"""Turning a QR code's reported angle into a page rotation. Pure; no PDFium."""


def quarter_turn_from_qr(qr_orientation: int) -> int:
    """Clockwise quarter turn (0, 90, 180 or 270) that makes a cover upright.

    zxing reports the code's exact angle, so a slightly tilted scan or phone photo gives values
    such as 1 or 359; page rotations are whole quarter turns (D-049), so snap to the nearest one.
    """
    clockwise = (-qr_orientation) % 360
    return (round(clockwise / 90) * 90) % 360
