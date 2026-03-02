// pe_col.sv
// Two PEs stacked vertically — psum flows downward.
// Both PEs share the same weight input (broadcast).
// Each PE has its own activation input.
//
//   act0, weight  →  [PE0]  →  psum = W×A0
//                                  ↓ psum_wire
//   act1, weight  →  [PE1]  →  psum_out = W×A0 + W×A1 = W×(A0+A1)

module pe_col #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH+1:0] act0_in,   // activation for PE0
    input  logic [DATA_WIDTH+1:0] act1_in,   // activation for PE1

    input  logic [DATA_WIDTH+1:0] weight_in, // broadcast to both PEs

    input  logic [ACC_WIDTH-1:0]  psum_in,   // fed into top of column
    output logic [ACC_WIDTH-1:0]  psum_out   // output from bottom of column
);

    logic [ACC_WIDTH-1:0] psum_mid;  // psum between PE0 and PE1

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe0 (
        .clk_i     (clk_i),
        .rst_i     (rst_i),
        .act_in    (act0_in),
        .act_out   (),
        .weight_in (weight_in),
        .weight_out(),
        .psum_in   (psum_in),
        .psum_out  (psum_mid)
    );

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe1 (
        .clk_i     (clk_i),
        .rst_i     (rst_i),
        .act_in    (act1_in),
        .act_out   (),
        .weight_in (weight_in),
        .weight_out(),
        .psum_in   (psum_mid),
        .psum_out  (psum_out)
    );

endmodule
