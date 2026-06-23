import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image
from io import BytesIO

def main():
    svg_path = Path("assets/icons/holographic_touch.svg")
    ico_path = Path("assets/icons/holographic_touch.ico")
    
    if not svg_path.exists():
        print(f"Error: {svg_path} does not exist.")
        sys.exit(1)
        
    print(f"Reading SVG from {svg_path}...")
    
    # We need a QApplication instance to initialize Qt graphics resources
    app = QApplication(sys.argv)
    
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print("Error: Invalid SVG file.")
        sys.exit(1)
        
    sizes = [16, 32, 48, 64, 128, 256]
    pil_images = []
    
    for size in sizes:
        print(f"Rendering size {size}x{size}...")
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(0) # Transparent background
        
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        
        # Convert QImage to PIL Image via memory buffer
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        
        pil_img = Image.open(BytesIO(ba.data()))
        pil_images.append(pil_img)
        
    print(f"Saving multi-size ICO to {ico_path}...")
    # Save the first image as base, append the rest, and specify sizes
    pil_images[0].save(
        str(ico_path),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=pil_images[1:]
    )
    print("Icon conversion successful!")

if __name__ == "__main__":
    main()
