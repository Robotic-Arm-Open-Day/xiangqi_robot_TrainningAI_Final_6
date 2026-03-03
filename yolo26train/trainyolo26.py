from ultralytics import YOLO
import torch

def execute_training_pipeline():
    # Auto-detect GPU, fall back to CPU
    device = 0 if torch.cuda.is_available() else "cpu"
    print(f"Training on: {'GPU (CUDA)' if device == 0 else 'CPU'}")

    # Initialize the YOLO26 Medium architecture
    model = YOLO("yolo26m.pt")
    
    # Execute the training loop
    results = model.train(
        data="dataset.yaml",
        epochs=80,
        close_mosaic=20,
        imgsz=640,
        batch=8,
        device=device, 
        project="chess_vision",
        name="yolo26_occupancy_run",
        workers=2,       # Must be 1-2 on Windows — avoids CUDA OOM in pin_memory workers

        # Augmentation
        mosaic=1.0,
        mixup=0.2,
        scale=0.7,
        translate=0.15,
        degrees=15.0,
        hsv_h=0.02,
        hsv_s=0.8,
        hsv_v=0.5,
        fliplr=0.5,
    )
    
if __name__ == "__main__":
    execute_training_pipeline()