"""Gesture data collector + trainer.

Usage:
  Step 1 - collect: python train_gesture_classifier.py --collect
  Step 2 - train:   python train_gesture_classifier.py --train

Collecting opens a window showing your camera. Press number keys to label
the current gesture, SPACE to save a sample, Q to quit.
"""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np

GESTURE_KEYS = {
    "1": "MOVE", "2": "LEFT_CLICK", "3": "RIGHT_CLICK",
    "4": "DOUBLE_CLICK", "5": "SCROLL", "6": "DRAG",
    "7": "PAUSE", "8": "KEYBOARD", "0": "NONE",
}
DATA_PATH = Path("gesture_training_data.npz")
MODEL_PATH = Path("gesture_model.pkl")
LABEL_PATH = Path("gesture_labels.json")


def collect():
    import cv2
    try:
        import mediapipe as mp
    except ImportError:
        print("mediapipe required for collection")
        return

    hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
    cap = cv2.VideoCapture(0)
    samples_X, samples_y = [], []
    current_label = "MOVE"
    count = 0

    print("Keys: 1=MOVE 2=LEFT_CLICK 3=RIGHT_CLICK 4=DOUBLE_CLICK")
    print("      5=SCROLL 6=DRAG 7=PAUSE 8=KEYBOARD 0=NONE")
    print("SPACE=save sample, Q=quit+save")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks:
            lms = result.multi_hand_landmarks[0].landmark
            xy = [(lm.x * frame.shape[1], lm.y * frame.shape[0]) for lm in lms]
            pts = np.asarray(xy, dtype=np.float32)
            wrist = pts[0].copy()
            pts -= wrist
            scale = float(np.linalg.norm(pts[9] - pts[0]) + 1e-6)
            pts /= scale
            features = pts.flatten()

            cv2.putText(frame, f"Label: {current_label}  Samples: {count}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            key = cv2.waitKey(1) & 0xFF
            if 0 <= key <= 255 and chr(key) in GESTURE_KEYS:
                current_label = GESTURE_KEYS[chr(key)]
            elif key == ord(' '):
                samples_X.append(features)
                samples_y.append(current_label)
                count += 1
                print(f"  Saved: {current_label} ({count} total)")

        cv2.imshow("Collect gestures", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if samples_X:
        np.savez(DATA_PATH, X=np.array(samples_X), y=np.array(samples_y))
        print(f"Saved {len(samples_X)} samples to {DATA_PATH}")


def train():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report
    from sklearn.model_selection import train_test_split

    if not DATA_PATH.exists():
        print(f"No data at {DATA_PATH}. Run --collect first.")
        return

    data = np.load(DATA_PATH, allow_pickle=True)
    X, y = data["X"], data["y"]
    labels = sorted(set(y))

    y_idx = np.array([labels.index(g) for g in y])
    X_tr, X_te, y_tr, y_te = train_test_split(X, y_idx, test_size=0.2, random_state=42)

    clf = RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
    clf.fit(X_tr, y_tr)

    y_pred = clf.predict(X_te)
    print(classification_report(y_te, y_pred, target_names=labels))

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)
    LABEL_PATH.write_text(json.dumps(labels))
    print(f"Model saved to {MODEL_PATH}  ({len(labels)} classes)")
    print(f"Test accuracy: {(y_pred == y_te).mean():.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.collect:
        collect()
    elif args.train:
        train()
    else:
        parser.print_help()
