from systolic_array_model import SystolicArray2x2


def run_test(A=None,B=None):
    if A is None:
        A = [[10, 2],
             [3, 4]]
    if B is None:
        B = [[5, 6],
             [7, 8]]

    sa = SystolicArray2x2(input_width=8, weight_width=8)
    sa.reset()
    
    expected = {
        "c00": A[0][0]*B[0][0] + A[0][1]*B[1][0],   # 19
        "c01": A[0][0]*B[0][1] + A[0][1]*B[1][1],   # 22
        "c10": A[1][0]*B[0][0] + A[1][1]*B[1][0],   # 43
        "c11": A[1][0]*B[0][1] + A[1][1]*B[1][1],   # 50
    }

    # NOTE: stream COLUMNS of A, ROWS of B
    cycles = [
        # cycle 0: A col 0, B row 0
        ([A[0][0], A[1][0]], [1, 1], [B[0][0], B[0][1]], [1, 1]),  # [1,3], [5,6]
        # cycle 1: A col 1, B row 1
        ([A[0][1], A[1][1]], [1, 1], [B[1][0], B[1][1]], [1, 1]),  # [2,4], [7,8]
        # drain cycles
        ([0, 0], [0, 0], [0, 0], [0, 0]),
        ([0, 0], [0, 0], [0, 0], [0, 0]),
    ]

    # Helper to grab the psum field from a PE's output dict
    def grab_psum(d):
        for k in d.keys():
            if "psum" in k:
                return d[k]
        return 0

    out = None

    # Initialize "previous" outputs so we can show Δpsum per cycle
    prev_out = {
        "pe00": {"pe_psum_o": 0},
        "pe01": {"pe_psum_o": 0},
        "pe10": {"pe_psum_o": 0},
        "pe11": {"pe_psum_o": 0},
    }

    for cycle, (a_west, a_valid, b_north, b_valid) in enumerate(cycles):
        out = sa.step(a_west, a_valid, b_north, b_valid)

        print(f"\n=== Cycle {cycle} ===")
        print(f"a_west = {a_west}, a_valid = {a_valid}")
        print(f"b_north = {b_north}, b_valid = {b_valid}")

        for name in ["pe00", "pe01", "pe10", "pe11"]:
            curr = out[name]
            prev = prev_out.get(name, {})

            psum_prev = grab_psum(prev)
            psum_now = grab_psum(curr)
            delta = psum_now - psum_prev

            print(
                f"{name}: psum_prev = {psum_prev:3}, "
                f"psum_now = {psum_now:3}, "
                f"contribution_this_cycle = {delta:3}"
            )

        # Update prev_out for next cycle
        prev_out = out

    pe00 = out["pe00"]
    pe01 = out["pe01"]
    pe10 = out["pe10"]
    pe11 = out["pe11"]

    got = {
        "c00": grab_psum(pe00),
        "c01": grab_psum(pe01),
        "c10": grab_psum(pe10),
        "c11": grab_psum(pe11),
    }

    print("\n===== EXPECTED vs GOT =====")
    for key in expected.keys():
        print(f"{key}: expected {expected[key]}, got {got[key]}")
    print("===========================\n")

    return expected, got


if __name__ == "__main__":
    run_test()

