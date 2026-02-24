import time
import sys

try:
    import robot_sdk_core
except ImportError:
    print("ERROR: robot_sdk_core module not found. Run this in your SDK directory.")
    sys.exit(1)

# Configuration
ROBOT_IP = "192.168.58.2"  # Change this to your FR5's actual IP
PULSE_DURATION = 3.0  # Seconds the electromagnet stays ON
COOLDOWN_DURATION = 2.0  # Seconds the electromagnet stays OFF
TEST_CYCLES = 5  # Number of times to pulse the relay


def run_diagnostic():
    print(f"--- Fairino Main Control Box DO Diagnostic ---")
    print(f"Connecting to robot at {ROBOT_IP}...")

    robot = robot_sdk_core.RPC(ROBOT_IP)
    time.sleep(2)

    if not robot.SDK_state:
        print("CRITICAL: Failed to connect to the robot SDK.")
        sys.exit(1)

    print("Connection established.")

    # Get the DO pin from the user to prevent accidental triggers
    try:
        do_id = int(input("Enter the Main Control Box DO Pin ID you wired the relay to (e.g., 1): "))
    except ValueError:
        print("Invalid input. Must be an integer.")
        sys.exit(1)

    print(f"\nStarting {TEST_CYCLES} pulse cycles on DO_{do_id}...")
    print("WARNING: Ensure hands are clear of the electromagnet.")

    try:
        for i in range(1, TEST_CYCLES + 1):
            print(f"\nCycle {i}/{TEST_CYCLES}")

            # Energize Relay -> Electromagnet ON
            print(f"  -> Setting DO_{do_id} to HIGH (1) - Electromagnet ON")
            err_on = robot.SetDO(id=do_id, status=1, block=1)
            if err_on != 0:
                print(f"  -> ERROR setting DO high: code {err_on}")

            time.sleep(PULSE_DURATION)

            # De-energize Relay -> Electromagnet OFF (Testing Flyback Diodes here)
            print(f"  -> Setting DO_{do_id} to LOW (0) - Electromagnet OFF")
            err_off = robot.SetDO(id=do_id, status=0, block=1)
            if err_off != 0:
                print(f"  -> ERROR setting DO low: code {err_off}")

            time.sleep(COOLDOWN_DURATION)

        print("\nDiagnostic complete. No controller crashes detected.")

    except KeyboardInterrupt:
        print("\nTest manually aborted. Forcing DO to LOW for safety...")
        robot.SetDO(id=do_id, status=0, block=1)

    except Exception as e:
        print(f"\nUnexpected error during execution: {e}")
        robot.SetDO(id=do_id, status=0, block=1)


if __name__ == "__main__":
    run_diagnostic()
