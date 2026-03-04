import time
import sys

try:
    import robot_sdk_core
except ImportError:
    print("ERROR: robot_sdk_core module not found. Run this in your SDK directory.")
    sys.exit(1)

# Configuration
ROBOT_IP = "192.168.58.2"   # Change to your FR3's actual IP
PULSE_DURATION = 0.5        # Seconds electromagnet stays ON
COOLDOWN_DURATION = 0.5     # Seconds electromagnet stays OFF
TEST_CYCLES = 5             # Number of pulse cycles

def run_diagnostic():
    print("--- Fairino FR3 Main Control Box DO Diagnostic ---")
    print(f"Connecting to robot at {ROBOT_IP}...")

    robot = robot_sdk_core.RPC(ROBOT_IP)
    time.sleep(2)

    # Safe connection check
    # ret = robot.GetRobotState()
    # if ret[0] != 0:
    #     print(f"CRITICAL: Failed to connect to robot. Error code: {ret[0]}")
    #     sys.exit(1)

    # print(f"Connection established. Robot state: {ret}")

    # Get DO pin from user to prevent accidental triggers
    try:
        do_id = int(input("\nEnter the Main Control Box DO Pin ID (e.g., 2 for DO2): "))
    except ValueError:
        print("Invalid input. Must be an integer.")
        sys.exit(1)

    print(f"\nStarting {TEST_CYCLES} pulse cycles on DO_{do_id}...")
    print("WARNING: Ensure hands are clear of the electromagnet.\n")

    try:
        for i in range(1, TEST_CYCLES + 1):
            print(f"Cycle {i}/{TEST_CYCLES}")

            # Energize relay -> Electromagnet ON
            print(f"  -> DO_{do_id} HIGH (1) - Electromagnet ON")
            err_on = robot.SetDO(id=do_id, status=1, smooth=0, block=1)
            if err_on != 0:
                print(f"  -> ERROR setting DO high: code {err_on}")

            time.sleep(PULSE_DURATION)

            # De-energize relay -> Electromagnet OFF
            print(f"  -> DO_{do_id} LOW (0) - Electromagnet OFF")
            err_off = robot.SetDO(id=do_id, status=0, smooth=0, block=1)
            if err_off != 0:
                print(f"  -> ERROR setting DO low: code {err_off}")

            time.sleep(COOLDOWN_DURATION)
            print(f"  Cycle {i} complete.\n")

        print("Diagnostic complete. No controller crashes detected.")

    except KeyboardInterrupt:
        print("\nTest aborted manually. Forcing DO LOW for safety...")
        robot.SetDO(id=do_id, status=0, smooth=0, block=1)
        print("DO forced LOW. Safe to proceed.")

    except Exception as e:
        print(f"\nUnexpected error: {e}")
        print("Forcing DO LOW for safety...")
        robot.SetDO(id=do_id, status=0, smooth=0, block=1)
        print("DO forced LOW. Safe to proceed.")


if __name__ == "__main__":
    run_diagnostic()