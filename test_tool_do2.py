"""
Test tín hiệu gắp từ Tool DO2.
Gửi tín hiệu ON/OFF qua SetToolDO (cổng trên đầu tool robot).
Cổng: DO2 (id=2)
"""
import time
import sys

try:
    import robot_sdk_core
except ImportError:
    print("ERROR: robot_sdk_core module not found.")
    sys.exit(1)

# Configuration
ROBOT_IP = "192.168.58.2"
TOOL_DO_ID = 2              # Cố định cổng Tool DO2
PULSE_DURATION = 3.0        # Giữ ON (giây)
COOLDOWN_DURATION = 2.0     # Giữ OFF (giây)
TEST_CYCLES = 5


def run_test():
    print(f"--- Test Tool DO{TOOL_DO_ID} (Gripper Signal) ---")
    print(f"Connecting to robot at {ROBOT_IP}...")

    robot = robot_sdk_core.RPC(ROBOT_IP)
    time.sleep(2)

    if not robot.SDK_state:
        print("CRITICAL: Failed to connect to the robot SDK.")
        sys.exit(1)

    print("✅ Connection established.")
    print(f"\nSẽ test {TEST_CYCLES} chu kỳ ON/OFF trên Tool DO{TOOL_DO_ID}")
    print("⚠️  Đảm bảo tay đã rời khỏi vùng gắp!\n")

    input("Bấm ENTER để bắt đầu test...")

    try:
        for i in range(1, TEST_CYCLES + 1):
            print(f"\n--- Chu kỳ {i}/{TEST_CYCLES} ---")

            # ON — Gắp (Bật điện)
            print(f"  🔴 Tool DO{TOOL_DO_ID} = ON (1) — Gripper CLOSE")
            err = robot.SetToolDO(id=TOOL_DO_ID, status=1, block=1)
            if err != 0:
                print(f"  ❌ Lỗi SetToolDO ON: code {err}")
            else:
                print(f"  ✅ OK")

            time.sleep(PULSE_DURATION)

            # OFF — Thả (Tắt điện)
            print(f"  🟢 Tool DO{TOOL_DO_ID} = OFF (0) — Gripper OPEN")
            err = robot.SetToolDO(id=TOOL_DO_ID, status=0, block=1)
            if err != 0:
                print(f"  ❌ Lỗi SetToolDO OFF: code {err}")
            else:
                print(f"  ✅ OK")

            time.sleep(COOLDOWN_DURATION)

        print(f"\n✅ Hoàn tất {TEST_CYCLES} chu kỳ test Tool DO{TOOL_DO_ID}.")

    except KeyboardInterrupt:
        print("\n⚠️ Test bị hủy. Đang tắt DO để an toàn...")
        robot.SetToolDO(id=TOOL_DO_ID, status=0, block=1)

    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
        robot.SetToolDO(id=TOOL_DO_ID, status=0, block=1)


if __name__ == "__main__":
    run_test()
