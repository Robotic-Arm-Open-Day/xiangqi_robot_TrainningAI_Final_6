# =============================================================================
# === FILE: config.py (CẤU HÌNH TOÀN HỆ THỐNG) ===
# =============================================================================

# --- THÔNG SỐ ROBOT & BÀN CỜ ---
# (Các tọa độ này sẽ được ghi đè bởi quy trình Hiệu chỉnh tự động, nhưng cứ để làm gốc)
BOARD_ORIGIN_X = 0.0
BOARD_ORIGIN_Y = 0.0
CELL_SIZE = 60.0

# Tọa độ bãi chứa quân bị ăn (X, Y, Z)
CAPTURE_BIN_X = -226.123
CAPTURE_BIN_Y = 225.024
CAPTURE_BIN_Z = 291.68  # [QUAN TRỌNG] Độ cao khi thả quân vào thùng

# Độ cao an toàn (mm)
SAFE_Z  = 217.227  # Bay trên cao
PICK_Z  =172.633  # Hạ xuống gắp (Cần đo thật chuẩn)
PLACE_Z = 176.578  # Hạ xuống đặt

# Cấu hình Kẹp (Gripper) - Tùy chỉnh theo loại van của bạn
GRIPPER_CLOSE = 1
GRIPPER_OPEN = 0
MOVE_SPEED = 50

# Góc xoay của đầu Robot (Rx, Ry, Rz)
ROTATION = [89.658,-0.394, 174.148] 

# Kết nối Robot
ROBOT_IP = "192.168.58.2"
DRY_RUN = True # Đổi thành True nếu muốn test code mà không cần bật Robot

# --- THÔNG SỐ AI ---
AI_THINK_TIME = 10.0  # [QUAN TRỌNG] Thời gian suy nghĩ tối đa (giây)
AI_DEPTH = 3         # Độ sâu mặc định (sẽ bị ghi đè bởi logic tự động)

# Giá trị quân cờ (Dùng cho hàm đánh giá)
PIECE_VALUES = {
    'K': 10000, 'R': 100, 'C': 50, 'N': 45, 'E': 20, 'A': 20, 'P': 9
}

# Tọa độ về nhà (Home) để né Camera
IDLE_X = -72.027
IDLE_Y = 200.248
IDLE_Z = 278.586  
