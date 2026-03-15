"""
ONyX SplashScreen — animated intro, 3 seconds total.
  0.0 – 1.9s : icon animation (ring → spokes → O)
  1.9 – 3.0s : background network propagation
  3.0 – 3.3s : fade-out → main window
"""
import math
import random
import time

from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush,
    QFont, QRadialGradient, QPolygonF,
)
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG   = "#06090d"
C_ACC  = (0, 200, 180)
C_ACC2 = (0, 229, 204)
C_DIM  = (14, 28, 22)      # "unlit" teal-black
C_DIM2 = (8,  18, 14)      # even darker for bg nodes

# ── Icon geometry (96×96 viewbox) ─────────────────────────────────────────────
NODE_POS   = [(48,22),(70,36),(70,60),(48,74),(26,60),(26,36)]
RING_EDGES = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0)]
SPOKE_TIPS = [(48,32),(60,41),(60,55),(48,64),(36,55),(36,41)]

# ── Timing (ms) ───────────────────────────────────────────────────────────────
T_RING      = 1200
T_SPOKES    = 1600
T_O         = 1900
T_BG_START  = 1900   # background propagation begins when O finishes
T_TOTAL     = 3000   # animation end
T_FADEOUT   = 300    # fade-out duration after T_TOTAL
EDGE_DUR    = T_RING // len(RING_EDGES)   # 200 ms per ring edge
BG_EDGE_DUR = 220    # ms for one background edge to propagate

# ── Helpers ────────────────────────────────────────────────────────────────────
def lerp(a, b, t):    return a + (b-a) * max(0.0, min(1.0, t))
def ease_out(t):       return 1-(1-max(0.,min(1.,t)))**2
def ease_in_out(t):    t=max(0.,min(1.,t)); return t*t*(3-2*t)
def lerpC(c1,c2,t):
    t=max(0.,min(1.,t))
    return tuple(int(c1[i]+(c2[i]-c1[i])*t) for i in range(3))


# ── Background network generator ──────────────────────────────────────────────
def build_bg_network(W, H, icon_cx, icon_cy, icon_r,
                     n_nodes=34, min_dist=52, seed=None):
    """
    Place n_nodes randomly, avoiding icon area and screen edges.
    Connect each node to its 3 nearest neighbours.
    Returns (nodes, edges) where edges is a set of frozenset pairs.
    """
    rng = random.Random(seed)
    PAD = 32
    nodes = []
    attempts = 0
    while len(nodes) < n_nodes and attempts < 8000:
        attempts += 1
        x = rng.uniform(PAD, W-PAD)
        y = rng.uniform(PAD, H-PAD)
        # Avoid icon circle
        if math.hypot(x-icon_cx, y-icon_cy) < icon_r:
            continue
        # Minimum spacing
        if any(math.hypot(x-nx, y-ny) < min_dist for nx,ny in nodes):
            continue
        nodes.append((x, y))

    # Build edges: each node → 3 nearest neighbours
    edges = set()
    for i, (x,y) in enumerate(nodes):
        dists = sorted(
            [(math.hypot(x-nx, y-ny), j) for j,(nx,ny) in enumerate(nodes) if j!=i]
        )
        for _, j in dists[:3]:
            edges.add(frozenset([i,j]))

    return nodes, list(edges)


def edge_key(i, j):
    return (min(i,j), max(i,j))


class SplashScreen(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(410, 670)
        self.setStyleSheet(f"background:{C_BG};")

        W, H = 410, 670

        # Icon position
        self._ICON_W  = 220
        self._off_x   = (W - self._ICON_W) / 2
        self._off_y   = (H - self._ICON_W) / 2 - 60
        self._icon_cx = W / 2
        self._icon_cy = self._off_y + self._ICON_W / 2

        # Icon animation state
        self._start_node  = random.randint(0,5)
        self._start_time  = None
        self._elapsed_ms  = 0
        self._done        = False
        self._fade_alpha  = 1.0

        # ── Build background network (fixed for this launch) ──────────────
        self._bg_nodes, self._bg_edges = build_bg_network(
            W, H,
            icon_cx  = self._icon_cx,
            icon_cy  = self._icon_cy,
            icon_r   = self._ICON_W * 0.56,
            n_nodes  = 34,
            min_dist = 52,
        )
        # Adjacency list
        self._adj = {i: [] for i in range(len(self._bg_nodes))}
        for e in self._bg_edges:
            a, b = tuple(e)
            self._adj[a].append(b)
            self._adj[b].append(a)

        # ── Background propagation state ──────────────────────────────────
        self._bg_node_lit   : set  = set()      # lit node indices
        self._bg_edge_prog  : dict = {}          # key→float 0..1
        self._bg_edge_start : dict = {}          # key→ms when started
        self._bg_visited    : set  = set()       # nodes already queued
        self._bg_started    = False

        # Opacity for fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(14)

    def showEvent(self, e):
        self._start_time = time.monotonic()
        super().showEvent(e)

    # ── Tick ───────────────────────────────────────────────────────────────
    def _tick(self):
        if self._start_time is None:
            return
        self._elapsed_ms = int((time.monotonic()-self._start_time)*1000)
        t = self._elapsed_ms

        # Start background propagation when O finishes
        if t >= T_BG_START and not self._bg_started:
            self._bg_started = True
            start = random.randrange(len(self._bg_nodes))
            self._bg_node_lit.add(start)
            self._bg_visited.add(start)
            for nb in self._adj[start]:
                k = edge_key(start, nb)
                self._bg_edge_start[k] = t
                self._bg_edge_prog[k]  = 0.0

        # Update background edge progress
        if self._bg_started:
            for k, t_start in list(self._bg_edge_start.items()):
                prog = (t - t_start) / BG_EDGE_DUR
                prog = ease_out(prog)
                self._bg_edge_prog[k] = prog
                if prog >= 1.0:
                    # Find the unlit end of this edge
                    a, b = k
                    for node in (a, b):
                        if node not in self._bg_node_lit:
                            self._bg_node_lit.add(node)
                            if node not in self._bg_visited:
                                self._bg_visited.add(node)
                                # Propagate to its other neighbours
                                for nb in self._adj[node]:
                                    k2 = edge_key(node, nb)
                                    if nb not in self._bg_node_lit and k2 not in self._bg_edge_start:
                                        self._bg_edge_start[k2] = t
                                        self._bg_edge_prog[k2]   = 0.0

        # Fade-out
        if t >= T_TOTAL:
            fade_t = (t - T_TOTAL) / T_FADEOUT
            self._fade_alpha = max(0.0, 1.0 - fade_t)
            self._opacity.setOpacity(self._fade_alpha)
            if self._fade_alpha <= 0.0 and not self._done:
                self._done = True
                self._timer.stop()
                self.finished.emit()
                self.close()
                return

        self.update()

    # ── Paint ──────────────────────────────────────────────────────────────
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C_BG))

        t = self._elapsed_ms

        # ════════════════════════════════════════════════════════════════════
        # BACKGROUND NETWORK
        # ════════════════════════════════════════════════════════════════════
        bg_nodes = self._bg_nodes
        bg_edges = self._bg_edges

        # Draw all background edges (dim baseline)
        for e_ in bg_edges:
            a, b = tuple(e_)
            ax, ay = bg_nodes[a]
            bx, by = bg_nodes[b]
            k = edge_key(a, b)
            prog = self._bg_edge_prog.get(k, 0.0)

            if prog <= 0:
                # Fully dim
                pen = QPen(QColor(*C_DIM2, 55), 0.7, Qt.PenStyle.DashLine)
                pen.setDashPattern([3.0, 3.0])
                p.setPen(pen)
                p.drawLine(QPointF(ax,ay), QPointF(bx,by))
            else:
                # Always draw dim base
                pen = QPen(QColor(*C_DIM2, 45), 0.7, Qt.PenStyle.DashLine)
                pen.setDashPattern([3.0, 3.0])
                p.setPen(pen)
                p.drawLine(QPointF(ax,ay), QPointF(bx,by))

                # Determine direction: which end is lit?
                a_lit = a in self._bg_node_lit
                b_lit = b in self._bg_node_lit
                if a_lit and not b_lit:
                    fx,fy,tx_,ty_ = ax,ay,bx,by
                elif b_lit and not a_lit:
                    fx,fy,tx_,ty_ = bx,by,ax,ay
                else:
                    fx,fy,tx_,ty_ = ax,ay,bx,by

                ex = fx + (tx_-fx)*prog
                ey = fy + (ty_-fy)*prog

                alpha = int(lerp(80, 190, prog))
                lit_pen = QPen(QColor(*C_ACC, alpha), 0.9, Qt.PenStyle.DashLine)
                lit_pen.setDashPattern([3.0, 2.5])
                p.setPen(lit_pen)
                p.drawLine(QPointF(fx,fy), QPointF(ex,ey))

        # Draw background nodes
        for i,(nx,ny) in enumerate(bg_nodes):
            if i in self._bg_node_lit:
                nd_r = 2.8
                col  = QColor(*C_ACC, 200)
                # Small glow
                grd = QRadialGradient(QPointF(nx,ny), nd_r*4)
                grd.setColorAt(0, QColor(*C_ACC2, 50))
                grd.setColorAt(1, QColor(*C_ACC2, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grd))
                p.drawEllipse(QPointF(nx,ny), nd_r*4, nd_r*4)
            else:
                nd_r = 2.2
                col  = QColor(*C_DIM2, 90)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(nx,ny), nd_r, nd_r)

        # ════════════════════════════════════════════════════════════════════
        # ICON ANIMATION
        # ════════════════════════════════════════════════════════════════════
        W, H    = self.width(), self.height()
        sc      = self._ICON_W / 96.0
        off_x   = self._off_x
        off_y   = self._off_y

        def vx(x): return off_x + x*sc
        def vy(y): return off_y + y*sc
        def vp(x,y): return QPointF(vx(x),vy(y))
        def vs(v): return v*sc

        # Compute icon animation state
        node_lit      = [False]*6
        node_lit[self._start_node] = True
        edge_progress = [0.0]*6

        for i in range(6):
            idx  = (self._start_node + i) % 6
            es   = i * EDGE_DUR
            ee   = (i+1) * EDGE_DUR
            if t >= ee:
                edge_progress[idx] = 1.0
                node_lit[(idx+1)%6] = True
            elif t >= es:
                edge_progress[idx] = ease_in_out((t-es)/EDGE_DUR)

        spoke_progress = 0.0
        if t >= T_RING:
            spoke_progress = ease_out((t-T_RING)/(T_SPOKES-T_RING))

        o_progress = 0.0
        if t >= T_SPOKES:
            o_progress = ease_out((t-T_SPOKES)/(T_O-T_SPOKES))

        # Octagon body
        oct_pts = [vp(x,y) for x,y in
                   [(30,8),(66,8),(88,30),(88,66),(66,88),(30,88),(8,66),(8,30)]]
        poly = QPolygonF(oct_pts)
        grd  = QRadialGradient(vp(40,34), vs(62))
        grd.setColorAt(0,    QColor(19,32,24))
        grd.setColorAt(0.55, QColor(4,12,8))
        grd.setColorAt(1,    QColor(2,4,6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grd))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(0,200,180,200), vs(1.2)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)

        # Chamfer lines
        chamfers = [((30,8),(36,20)),((66,8),(60,20)),((88,30),(76,36)),
                    ((88,66),(76,60)),((66,88),(60,76)),((30,88),(36,76)),
                    ((8,66),(20,60)),((8,30),(20,36))]
        p.setPen(QPen(QColor(0,200,180,100), vs(0.5)))
        for a_,b_ in chamfers:
            p.drawLine(vp(*a_),vp(*b_))

        # Inner octagon
        ip = [vp(x,y) for x,y in
              [(34,18),(62,18),(78,34),(78,62),(62,78),(34,78),(18,62),(18,34)]]
        p.setPen(QPen(QColor(0,200,180,60), vs(0.5)))
        p.drawPolygon(QPolygonF(ip))

        # Orbit dashed ring (dim)
        orb_r = vs(26)
        p.setPen(QPen(QColor(*C_DIM,80), vs(0.6), Qt.PenStyle.DashLine))
        p.drawEllipse(QRectF(vx(48)-orb_r,vy(48)-orb_r,orb_r*2,orb_r*2))

        # Ring edges
        for i,(nf,nt) in enumerate(RING_EDGES):
            prog = edge_progress[i]
            if prog <= 0: continue
            fx,fy = NODE_POS[nf]; tx_,ty_ = NODE_POS[nt]
            ex = fx+(tx_-fx)*prog; ey = fy+(ty_-fy)*prog
            dp = QPen(QColor(0,200,180,200), vs(0.8), Qt.PenStyle.DashLine)
            dp.setDashPattern([3.0,2.5]); p.setPen(dp)
            p.drawLine(vp(fx,fy),vp(ex,ey))

        # Spokes
        for i in range(6):
            if spoke_progress <= 0: break
            nx_,ny_ = NODE_POS[i]; tx_,ty_ = SPOKE_TIPS[i]
            ex=nx_+(tx_-nx_)*spoke_progress; ey=ny_+(ty_-ny_)*spoke_progress
            p.setPen(QPen(QColor(0,200,180,int(160*spoke_progress)), vs(0.7)))
            p.drawLine(vp(nx_,ny_),vp(ex,ey))

        # Node dots
        for i,(nx_,ny_) in enumerate(NODE_POS):
            if node_lit[i]:
                col = QColor(*C_ACC2,230); rd=vs(2.2 if i in(0,3) else 1.8)
                grd2=QRadialGradient(vp(nx_,ny_),rd*3)
                grd2.setColorAt(0,QColor(*C_ACC2,70)); grd2.setColorAt(1,QColor(*C_ACC2,0))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(grd2))
                p.drawEllipse(vp(nx_,ny_),rd*3,rd*3)
            else:
                col=QColor(*C_DIM,100); rd=vs(1.8 if i in(0,3) else 1.5)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(col))
            p.drawEllipse(vp(nx_,ny_),rd,rd)

        # O oval
        ow,oh = vs(13),vs(16)
        o_rect = QRectF(vx(48)-ow,vy(48)-oh,ow*2,oh*2)

        if o_progress > 0:
            grd3=QRadialGradient(vp(48,48),ow*(1.6+o_progress*0.5))
            grd3.setColorAt(0,QColor(0,200,180,int(55*o_progress)))
            grd3.setColorAt(0.5,QColor(0,200,180,int(20*o_progress)))
            grd3.setColorAt(1,QColor(0,200,180,0))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(grd3))
            p.drawEllipse(vp(48,48),ow*(1.6+o_progress*0.5),ow*(1.6+o_progress*0.5))

        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(2,10,7,240)))
        p.drawEllipse(o_rect)

        sw = max(1,int(vs(2.8)))
        if o_progress>0:
            sc2=QColor(*lerpC(C_DIM,C_ACC2,o_progress),int(lerp(60,230,o_progress)))
        else:
            sc2=QColor(*C_DIM,60)
        p.setPen(QPen(sc2,sw)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(o_rect)

        rp=sw+max(1,int(vs(1.5)))
        p.setPen(QPen(QColor(*C_ACC,int(lerp(20,90,o_progress))),max(1,int(vs(0.8)))))
        p.drawEllipse(o_rect.adjusted(rp,rp,-rp,-rp))

        if o_progress>0:
            gp_=sw//2
            p.setPen(QPen(QColor(*C_ACC2,int(180*ease_out(o_progress))),
                          max(1,int(vs(1.4))),Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(o_rect.adjusted(gp_,gp_,-gp_,-gp_).toRect(),210*16,110*16)

        # Logo text
        ta = min(255,int(255*(t/800.)))
        f_=QFont("Courier New",28,QFont.Weight.Bold); p.setFont(f_)
        p.setPen(QColor(0,229,204,ta))
        p.drawText(QRectF(0,off_y+self._ICON_W+24,W,44),
                   Qt.AlignmentFlag.AlignHCenter,"ONyX")
        f2_=QFont("Courier New",11); p.setFont(f2_)
        p.setPen(QColor(110,143,168,min(200,ta)))
        p.drawText(QRectF(0,off_y+self._ICON_W+70,W,24),
                   Qt.AlignmentFlag.AlignHCenter,"Secure Network")

        p.end()
