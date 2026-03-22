"""
ONyX SplashScreen.
Only the main logo remains animated; the background stays static.
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

# Palette
C_BG   = "#06090d"
C_ACC  = (0, 200, 180)
C_ACC2 = (0, 229, 204)
C_DIM  = (14, 28, 22)      # "unlit" teal-black
C_DIM2 = (8,  18, 14)      # even darker for bg nodes

# Icon geometry (96x96 viewbox)
NODE_POS   = [(48,22),(70,36),(70,60),(48,74),(26,60),(26,36)]
RING_EDGES = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0)]
SPOKE_TIPS = [(48,32),(60,41),(60,55),(48,64),(36,55),(36,41)]

# Timing (ms)
T_RING      = 1200
T_SPOKES    = 1600
T_O         = 1900
T_TOTAL     = 4000   # animation end
T_FADEOUT   = 300    # fade-out duration after T_TOTAL
EDGE_DUR    = T_RING // len(RING_EDGES)   # 200 ms per ring edge

# Helpers
def lerp(a, b, t):    return a + (b-a) * max(0.0, min(1.0, t))
def ease_out(t):       return 1-(1-max(0.,min(1.,t)))**2
def ease_in_out(t):    t=max(0.,min(1.,t)); return t*t*(3-2*t)
def lerpC(c1,c2,t):
    t=max(0.,min(1.,t))
    return tuple(int(c1[i]+(c2[i]-c1[i])*t) for i in range(3))


# Background network generator
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
        if math.hypot(x-icon_cx, y-icon_cy) < icon_r:
            continue
        if any(math.hypot(x-nx, y-ny) < min_dist for nx,ny in nodes):
            continue
        nodes.append((x, y))

    edges = set()
    for i, (x,y) in enumerate(nodes):
        dists = sorted(
            [(math.hypot(x-nx, y-ny), j) for j,(nx,ny) in enumerate(nodes) if j!=i]
        )
        for _, j in dists[:3]:
            edges.add(frozenset([i,j]))

    return nodes, list(edges)


class SplashScreen(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(410, 760)
        self.setStyleSheet(f"background:{C_BG};")

        W, H = 410, 760

        self._ICON_W  = 220
        self._off_x   = (W - self._ICON_W) / 2
        self._off_y   = (H - self._ICON_W) / 2 - 60

        self._start_node  = random.randint(0,5)
        self._start_time  = None
        self._elapsed_ms  = 0
        self._done        = False
        self._fade_alpha  = 1.0

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(14)

    def showEvent(self, e):
        self._start_time = time.monotonic()
        super().showEvent(e)

    def _tick(self):
        if self._start_time is None:
            return
        self._elapsed_ms = int((time.monotonic()-self._start_time)*1000)
        t = self._elapsed_ms

        if t >= T_TOTAL:
            fade_t = (t - T_TOTAL) / T_FADEOUT
            self._fade_alpha = max(0.0, 1.0 - fade_t)
            self._opacity.setOpacity(self._fade_alpha)
            if self._fade_alpha <= 0.0 and not self._done:
                self._done = True
                self._timer.stop()
                self.finished.emit()
                return

        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C_BG))

        t = self._elapsed_ms
        W = self.width()
        sc = self._ICON_W / 96.0
        off_x = self._off_x
        off_y = self._off_y

        def vx(x): return off_x + x*sc
        def vy(y): return off_y + y*sc
        def vp(x,y): return QPointF(vx(x),vy(y))
        def vs(v): return v*sc

        node_lit = [False]*6
        node_lit[self._start_node] = True
        edge_progress = [0.0]*6

        for i in range(6):
            idx = (self._start_node + i) % 6
            es = i * EDGE_DUR
            ee = (i+1) * EDGE_DUR
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

        chamfers = [((30,8),(36,20)),((66,8),(60,20)),((88,30),(76,36)),
                    ((88,66),(76,60)),((66,88),(60,76)),((30,88),(36,76)),
                    ((8,66),(20,60)),((8,30),(20,36))]
        p.setPen(QPen(QColor(0,200,180,100), vs(0.5)))
        for a_,b_ in chamfers:
            p.drawLine(vp(*a_),vp(*b_))

        ip = [vp(x,y) for x,y in
              [(34,18),(62,18),(78,34),(78,62),(62,78),(34,78),(18,62),(18,34)]]
        p.setPen(QPen(QColor(0,200,180,60), vs(0.5)))
        p.drawPolygon(QPolygonF(ip))

        orb_r = vs(26)
        p.setPen(QPen(QColor(*C_DIM,80), vs(0.6), Qt.PenStyle.DashLine))
        p.drawEllipse(QRectF(vx(48)-orb_r,vy(48)-orb_r,orb_r*2,orb_r*2))

        for i,(nf,nt) in enumerate(RING_EDGES):
            prog = edge_progress[i]
            if prog <= 0:
                continue
            fx,fy = NODE_POS[nf]
            tx_,ty_ = NODE_POS[nt]
            ex = fx+(tx_-fx)*prog
            ey = fy+(ty_-fy)*prog
            dp = QPen(QColor(0,200,180,200), vs(0.8), Qt.PenStyle.DashLine)
            dp.setDashPattern([3.0,2.5])
            p.setPen(dp)
            p.drawLine(vp(fx,fy),vp(ex,ey))

        for i in range(6):
            if spoke_progress <= 0:
                break
            nx_,ny_ = NODE_POS[i]
            tx_,ty_ = SPOKE_TIPS[i]
            ex = nx_+(tx_-nx_)*spoke_progress
            ey = ny_+(ty_-ny_)*spoke_progress
            p.setPen(QPen(QColor(0,200,180,int(160*spoke_progress)), vs(0.7)))
            p.drawLine(vp(nx_,ny_),vp(ex,ey))

        for i,(nx_,ny_) in enumerate(NODE_POS):
            if node_lit[i]:
                col = QColor(*C_ACC2,230)
                rd = vs(2.2 if i in(0,3) else 1.8)
                grd2 = QRadialGradient(vp(nx_,ny_),rd*3)
                grd2.setColorAt(0,QColor(*C_ACC2,70))
                grd2.setColorAt(1,QColor(*C_ACC2,0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grd2))
                p.drawEllipse(vp(nx_,ny_),rd*3,rd*3)
            else:
                col = QColor(*C_DIM,100)
                rd = vs(1.8 if i in(0,3) else 1.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(vp(nx_,ny_),rd,rd)

        ow,oh = vs(13),vs(16)
        o_rect = QRectF(vx(48)-ow,vy(48)-oh,ow*2,oh*2)

        if o_progress > 0:
            grd3 = QRadialGradient(vp(48,48),ow*(1.6+o_progress*0.5))
            grd3.setColorAt(0,QColor(0,200,180,int(55*o_progress)))
            grd3.setColorAt(0.5,QColor(0,200,180,int(20*o_progress)))
            grd3.setColorAt(1,QColor(0,200,180,0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grd3))
            p.drawEllipse(vp(48,48),ow*(1.6+o_progress*0.5),ow*(1.6+o_progress*0.5))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(2,10,7,240)))
        p.drawEllipse(o_rect)

        sw = max(1,int(vs(2.8)))
        if o_progress>0:
            sc2 = QColor(*lerpC(C_DIM,C_ACC2,o_progress),int(lerp(60,230,o_progress)))
        else:
            sc2 = QColor(*C_DIM,60)
        p.setPen(QPen(sc2,sw))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(o_rect)

        rp = sw+max(1,int(vs(1.5)))
        p.setPen(QPen(QColor(*C_ACC,int(lerp(20,90,o_progress))),max(1,int(vs(0.8)))))
        p.drawEllipse(o_rect.adjusted(rp,rp,-rp,-rp))

        if o_progress>0:
            gp_ = sw//2
            p.setPen(QPen(QColor(*C_ACC2,int(180*ease_out(o_progress))),
                          max(1,int(vs(1.4))),Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(o_rect.adjusted(gp_,gp_,-gp_,-gp_).toRect(),210*16,110*16)

        f_ = QFont("Courier New",28,QFont.Weight.Bold)
        p.setFont(f_)
        p.setPen(QColor(0,229,204,255))
        p.drawText(QRectF(0,off_y+self._ICON_W+24,W,44),
                   Qt.AlignmentFlag.AlignHCenter,"ONyX")
        f2_ = QFont("Courier New",11)
        p.setFont(f2_)
        p.setPen(QColor(110,143,168,200))
        p.drawText(QRectF(0,off_y+self._ICON_W+70,W,24),
                   Qt.AlignmentFlag.AlignHCenter,"Secure Network")

        p.end()
