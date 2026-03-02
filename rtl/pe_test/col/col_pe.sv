module pe_col #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH-1:0] act0_in,
    input  logic [DATA_WIDTH-1:0] act1_in,

    input  logic [DATA_WIDTH+1:0] weight_in,   // enters at top

    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);

    logic [DATA_WIDTH+1:0] weight_mid;  // weight_out of PE0 -> weight_in of PE1
    logic [ACC_WIDTH-1:0]  psum_mid;

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe0 (
        .clk_i     (clk_i),
        .rst_i     (rst_i),
        .act_in    (act0_in),
        .act_out   (),
        .weight_in (weight_in),
        .weight_out(weight_mid),   // flows down to PE1
        .psum_in   (psum_in),
        .psum_out  (psum_mid)
    );

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe1 (
        .clk_i     (clk_i),
        .rst_i     (rst_i),
        .act_in    (act1_in),
        .act_out   (),
        .weight_in (weight_mid),   // receives from PE0
        .weight_out(),
        .psum_in   (psum_mid),
        .psum_out  (psum_out)
    );

endmodule
