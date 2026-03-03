module pe_row #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH-1:0] act_in,      // activation enters left, flows right

    input  logic [DATA_WIDTH-1:0] weight0_in,   // weight for PE0, from above
    input  logic [DATA_WIDTH-1:0] weight1_in,   // weight for PE1, from above
    input  logic                  weight_valid0,  // broadcast latch into shadow buffer
    input  logic                  weight_valid1,
    input  logic                  buf_sel0,      // active buffer select for PE0
    input  logic                  buf_sel1,      // active buffer select for PE1

    input  logic [ACC_WIDTH-1:0]  psum0_in,     // PE0 partial sum input
    input  logic [ACC_WIDTH-1:0]  psum1_in,     // PE1 partial sum input

    output logic [ACC_WIDTH-1:0]  psum0_out,    // PE0 independent output
    output logic [ACC_WIDTH-1:0]  psum1_out     // PE1 independent output
);

    logic [DATA_WIDTH-1:0] act_mid;   // act_out of PE0 -> act_in of PE1

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe0 (
        .clk_i       (clk_i),
        .rst_i       (rst_i),
        .act_in      (act_in),
        .act_out     (act_mid), //shifting left       
        .weight_in   (weight0_in),
        .weight_out  (),
        .weight_latch(weight_valid0),
        .buf_sel     (buf_sel0),
        .psum_in     (psum0_in),
        .psum_out    (psum0_out)
    );

    pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) u_pe1 (
        .clk_i       (clk_i),
        .rst_i       (rst_i),
        .act_in      (act_mid),       
        .act_out     (),
        .weight_in   (weight1_in),    
        .weight_out  (),
        .weight_latch(weight_valid1),
        .buf_sel     (buf_sel1),
        .psum_in     (psum1_in),
        .psum_out    (psum1_out)
    );

endmodule
