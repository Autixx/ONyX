"""
ONyX SplashScreen — animated intro, 2 seconds.
Import and use: splash = SplashScreen(); splash.finished.connect(show_main); splash.show()
"""
import math
import random
import time

from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QRadialGradient,
    QFont, QLinearGradient,
)
from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect, QApplication

# Palette
C_BG   = "#06090d"
C_ACC  = (0, 200, 180)
C_ACC2 = (0, 229, 204)
C_DIM  = (20, 40, 35)     # dark teal — "unlit" element colour
C_T2   = (58, 82, 104)

# Icon geometry in 96x96 viewbox space
NODE_POS = [(48,22),(70,36),(70,60),(48,74),(26,60),(26,36)]   # 0-5 clockwise from top
RING_EDGES  = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0)]
SPOKE_TIPS  = [(48,32),(60,41),(60,55),(48,64),(36,55),(36,41)] # inner end of each spoke

# Animation timing (milliseconds)
T_TOTAL       = 2000
T_RING        = 1200   # 0 → 1200 : ring edges light up
T_SPOKES      = 1600   # 1200 → 1600 : spokes animate inward
T_O           = 1900   # 1600 → 1900 : O lights up
T_HOLD        = 2000   # 1900 → 2000 : hold
EDGE_DUR      = T_RING // len(RING_EDGES)   # 200ms per edge


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t

def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

def ease_out(t):
    return 1 - (1 - t) ** 2

def ease_in_out(t):
    return t*t*(3-2*t)


class SplashScreen(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.Window |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(410, 670)
        self.setStyleSheet(f"background: {C_BG};")

        self._start_node = random.randint(0, 5)
        self._elapsed_ms  = 0
        self._done        = False
        self._fade_out    = False
        self._fade_alpha  = 1.0
        self._start_time  = None

        # Opacity effect for final fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def showEvent(self, e):
        self._start_time = time.monotonic()
        super().showEvent(e)

    # ── Timer tick ─────────────────────────────────────────────────────────

    def _tick(self):
        if self._start_time is None:
            return
        self._elapsed_ms = int((time.monotonic() - self._start_time) * 1000)

        if self._elapsed_ms >= T_TOTAL and not self._fade_out:
            self._fade_out = True

        if self._fade_out:
            self._fade_alpha = max(0.0, 1.0 - (self._elapsed_ms - T_TOTAL) / 300.0)
            self._opacity.setOpacity(self._fade_alpha)
            if self._fade_alpha <= 0.0 and not self._done:
                self._done = True
                self._timer.stop()
                self.finished.emit()
                self.close()
                return

        self.update()

    # ── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C_BG))

        W, H    = self.width(), self.height()
        ICON_W  = 220          # icon render size in widget pixels
        off_x   = (W - ICON_W) / 2
        off_y   = (H - ICON_W) / 2 - 60   # slightly above centre

        # Scale: SVG viewbox 96 → ICON_W px
        sc = ICON_W / 96.0

        def vx(x): return off_x + x * sc
        def vy(y): return off_y + y * sc
        def vp(x, y): return QPointF(vx(x), vy(y))
        def vs(v): return v * sc

        t = self._elapsed_ms

        # ── Compute animation state ─────────────────────────────────────

        # Which nodes are lit
        node_lit = [False] * 6
        node_lit[self._start_node] = True   # start node always lit from t=0

        # Per-edge draw progress (0.0 → 1.0)
        edge_progress = [0.0] * 6

        for i in range(6):
            idx = (self._start_node + i) % 6
            edge_start_ms = i * EDGE_DUR
            edge_end_ms   = (i+1) * EDGE_DUR
            if t >= edge_end_ms:
                edge_progress[idx] = 1.0
                # destination node lights up
                dest = (idx + 1) % 6
                node_lit[dest] = True
            elif t >= edge_start_ms:
                edge_progress[idx] = ease_in_out(
                    (t - edge_start_ms) / EDGE_DUR)

        # Spoke progress (all 6 simultaneously)
        spoke_progress = 0.0
        if t >= T_RING:
            spoke_progress = ease_out((t - T_RING) / (T_SPOKES - T_RING))

        # O progress
        o_progress = 0.0
        if t >= T_SPOKES:
            o_progress = ease_out((t - T_SPOKES) / (T_O - T_SPOKES))

        # ── Draw octagon body ───────────────────────────────────────────

        oct_pts = [vp(x, y) for x, y in
                   [(30,8),(66,8),(88,30),(88,66),(66,88),(30,88),(8,66),(8,30)]]
        from PyQt6.QtGui import QPolygonF
        poly = QPolygonF(oct_pts)

        # Radial gradient fill
        grad = QRadialGradient(vp(40, 34), vs(62))
        grad.setColorAt(0,   QColor(19, 32, 24))
        grad.setColorAt(0.55,QColor(4, 12, 8))
        grad.setColorAt(1,   QColor(2, 4, 6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPolygon(poly)

        # Octagon border
        pen = QPen(QColor(0,200,180,200), vs(1.2))
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)

        # Chamfer lines
        chamfers = [((30,8),(36,20)),((66,8),(60,20)),((88,30),(76,36)),
                    ((88,66),(76,60)),((66,88),(60,76)),((30,88),(36,76)),
                    ((8,66),(20,60)),((8,30),(20,36))]
        p.setPen(QPen(QColor(0,200,180,100), vs(0.5)))
        for a,b_ in chamfers:
            p.drawLine(vp(*a), vp(*b_))

        # Inner octagon
        inner_pts = [vp(x,y) for x,y in
                     [(34,18),(62,18),(78,34),(78,62),(62,78),(34,78),(18,62),(18,34)]]
        p.setPen(QPen(QColor(0,200,180,60), vs(0.5)))
        p.drawPolygon(QPolygonF(inner_pts))

        # ── Orbit dashed ring (static, dim) ────────────────────────────

        orb_r = vs(26)
        p.setPen(QPen(QColor(*C_DIM, 80), vs(0.6), Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(vx(48)-orb_r, vy(48)-orb_r, orb_r*2, orb_r*2))

        # ── Ring edges (animated dashes) ────────────────────────────────

        for i, (n_from, n_to) in enumerate(RING_EDGES):
            prog = edge_progress[i]
            if prog <= 0: continue

            fx, fy = NODE_POS[n_from]
            tx, ty = NODE_POS[n_to]
            # Current endpoint
            ex = fx + (tx-fx)*prog
            ey = fy + (ty-fy)*prog

            col = QColor(0,200,180,200)
            dash_pen = QPen(col, vs(0.8), Qt.PenStyle.DashLine)
            dash_pen.setDashPattern([3.0, 2.5])
            p.setPen(dash_pen)
            p.drawLine(vp(fx, fy), vp(ex, ey))

        # ── Spokes (animated solid lines from node toward center) ────────

        for i in range(6):
            if spoke_progress <= 0: break
            nx, ny = NODE_POS[i]
            tx, ty = SPOKE_TIPS[i]
            ex = nx + (tx-nx)*spoke_progress
            ey = ny + (ty-ny)*spoke_progress

            alpha = int(160 * spoke_progress)
            p.setPen(QPen(QColor(0,200,180,alpha), vs(0.7)))
            p.drawLine(vp(nx,ny), vp(ex,ey))

        # ── Network node dots ────────────────────────────────────────────

        for i, (nx, ny) in enumerate(NODE_POS):
            if node_lit[i]:
                col = QColor(*C_ACC2, 230)
                r_dot = vs(2.2) if i in (0,3) else vs(1.8)
            else:
                col = QColor(*C_DIM, 100)
                r_dot = vs(1.8) if i in (0,3) else vs(1.5)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(vx(nx), vy(ny)), r_dot, r_dot)

            # Small glow for lit nodes
            if node_lit[i]:
                glow_r = r_dot * 3
                grd = QRadialGradient(QPointF(vx(nx), vy(ny)), glow_r)
                grd.setColorAt(0, QColor(0,229,204,60))
                grd.setColorAt(1, QColor(0,229,204,0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grd))
                p.drawEllipse(QPointF(vx(nx), vy(ny)), glow_r, glow_r)

        # ── O oval ───────────────────────────────────────────────────────

        ow, oh = vs(13), vs(16)
        o_rect = QRectF(vx(48)-ow, vy(48)-oh, ow*2, oh*2)

        if o_progress > 0:
            # Glow behind O
            glow_r = ow * (1.5 + o_progress * 0.5)
            grd = QRadialGradient(QPointF(vx(48), vy(48)), glow_r)
            grd.setColorAt(0,   QColor(0,200,180, int(50*o_progress)))
            grd.setColorAt(0.5, QColor(0,200,180, int(20*o_progress)))
            grd.setColorAt(1,   QColor(0,200,180, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grd))
            p.drawEllipse(QPointF(vx(48),vy(48)), glow_r, glow_r)

        # O dark fill (always present)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(2,10,7,240)))
        p.drawEllipse(o_rect)

        # O stroke — starts dim, lights up with o_progress
        sw = max(1, int(vs(2.8)))
        if o_progress > 0:
            stroke_col = QColor(*lerp_color(C_DIM, C_ACC2, o_progress),
                                int(lerp(60, 230, o_progress)))
        else:
            stroke_col = QColor(*C_DIM, 60)
        p.setPen(QPen(stroke_col, sw))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(o_rect)

        # O inner ring
        rp = sw + max(1, int(vs(1.5)))
        inner_rect = o_rect.adjusted(rp, rp, -rp, -rp)
        inner_alpha = int(lerp(20, 90, o_progress))
        p.setPen(QPen(QColor(*C_ACC, inner_alpha), max(1, int(vs(0.8)))))
        p.drawEllipse(inner_rect)

        # Gleam arc on O
        if o_progress > 0:
            from PyQt6.QtCore import QRect
            gleam_pad = sw // 2
            gleam_rect = o_rect.adjusted(gleam_pad, gleam_pad, -gleam_pad, -gleam_pad)
            gleam_alpha = int(180 * ease_out(o_progress))
            p.setPen(QPen(QColor(*C_ACC2, gleam_alpha),
                          max(1, int(vs(1.4))),
                          Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(gleam_rect.toRect(), 210*16, 110*16)

        # ── Logo text below icon ─────────────────────────────────────────

        text_y = off_y + ICON_W + 24
        text_alpha = min(255, int(255 * (t / 800.0)))

        f_logo = QFont("Courier New", 28, QFont.Weight.Bold)
        p.setFont(f_logo)
        p.setPen(QColor(0, 229, 204, text_alpha))
        p.drawText(QRectF(0, text_y, W, 44),
                   Qt.AlignmentFlag.AlignHCenter, "ONyX")

        f_sub = QFont("Courier New", 11)
        p.setFont(f_sub)
        p.setPen(QColor(110, 143, 168, min(200, text_alpha)))
        p.drawText(QRectF(0, text_y+46, W, 24),
                   Qt.AlignmentFlag.AlignHCenter, "Secure Network")

        p.end()
