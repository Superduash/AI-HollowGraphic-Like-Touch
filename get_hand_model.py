"""Download the hand landmark ONNX model from PINTO0309's model zoo.
Run once: python get_hand_model.py
"""
import urllib.request, sys, pathlib
URL = "https://github.com/PINTO0309/PINTO_model_zoo/raw/main/257_MediaPipe_Hands/resources/hand_landmark_lite.onnx"
OUT = pathlib.Path("hand_landmark_lite.onnx")
if OUT.exists():
    print(f"Already exists: {OUT}")
    sys.exit(0)
print(f"Downloading {URL} ...")
urllib.request.urlretrieve(URL, OUT)
print(f"Saved to {OUT} ({OUT.stat().st_size // 1024} KB)")
