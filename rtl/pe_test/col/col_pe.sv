module pe_col #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH:0] act0_in,
    input  logic [DATA_WIDTH:0] act1_in,

    input  logic [DATA_WIDTH:0] weight_in,   // enters at top, flows down

    input  logic weight_valid,
    input  logic act0_valid,
    input  logic act1_valid,
    
    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);

    logic [DATA_WIDTH:0] weight_mid;  // weight_out of PE0 -> weight_in of PE1
    logic [ACC_WIDTH-1:0]  psum_mid;
    logic weight_valid_t;

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe0 (
        .clk_i     (clk_i),
        .rst_i     (rst_i),
        .act_in    (act0_in),
        .act_out   (),
        .weight_in (weight_in),
        .weight_out(weight_mid),   // flows down to PE1
        .weight_valid (weight_valid),
        .weight_valid_o (weight_valid_t),
        .act_valid_o (),
        .act_valid (act0_valid),
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
        .weight_valid (weight_valid_t),
        .weight_valid_o (),
        .act_valid_o (),
        .act_valid (act1_valid),
        .psum_in   (psum_mid),
        .psum_out  (psum_out)
    );

endmodule
