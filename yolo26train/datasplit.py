import os
import shutil
import random

# Anchor all paths to the PROJECT ROOT (one level up from yolo26train/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def build_yolo_pipeline(raw_dir="rawdata", target_dir="chess_dataset", split_ratio=0.8):
    # Resolve paths relative to the script's location
    raw_dir    = os.path.join(BASE_DIR, raw_dir)
    target_dir = os.path.join(BASE_DIR, target_dir)

    img_dir = os.path.join(raw_dir, "images")
    lbl_dir = os.path.join(raw_dir, "labels")

    # Validate source folders exist
    if not os.path.isdir(img_dir):
        raise FileNotFoundError(f"Images folder not found: {img_dir}")
    if not os.path.isdir(lbl_dir):
        raise FileNotFoundError(f"Labels folder not found: {lbl_dir}")

    # Create the YOLO directory structure
    for split in ("train", "val"):
        os.makedirs(os.path.join(target_dir, "images", split), exist_ok=True)
        os.makedirs(os.path.join(target_dir, "labels", split), exist_ok=True)

    # Gather, shuffle, and split
    images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    random.shuffle(images)

    split_index = int(len(images) * split_ratio)
    splits = {
        "train": images[:split_index],
        "val":   images[split_index:]
    }

    # Copy images + labels into the correct folders
    label_missing = 0
    for split_name, file_list in splits.items():
        for img_file in file_list:
            shutil.copy(
                os.path.join(img_dir, img_file),
                os.path.join(target_dir, "images", split_name, img_file)
            )
            lbl_file = os.path.splitext(img_file)[0] + ".txt"
            src_lbl  = os.path.join(lbl_dir, lbl_file)
            if os.path.exists(src_lbl):
                shutil.copy(src_lbl, os.path.join(target_dir, "labels", split_name, lbl_file))
            else:
                label_missing += 1

    # Summary
    print("\n=== Dataset Split Complete ===")
    print(f"  Source      : {raw_dir}")
    print(f"  Output      : {target_dir}")
    print(f"  Total images: {len(images)}")
    print(f"  Train       : {len(splits['train'])} images")
    print(f"  Val         : {len(splits['val'])} images")
    if label_missing:
        print(f"  WARNING     : {label_missing} image(s) had no matching label file!")
    print("==============================\n")

if __name__ == "__main__":
    build_yolo_pipeline()
