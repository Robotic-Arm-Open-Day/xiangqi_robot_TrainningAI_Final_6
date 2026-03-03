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
        epochs=50,
        imgsz=640,
        batch=4,
        device=device,
        project="chess_vision",
        name="yolo26_occupancy_run",
        workers=0        # Must be 0 on Windows — avoids CUDA OOM in pin_memory workers
    )
    
if __name__ == "__main__":
    execute_training_pipeline()