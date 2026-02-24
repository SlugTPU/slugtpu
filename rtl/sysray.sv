module systolic_array #(
    parameter N          = 4,
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                                    clk_i,
    input  logic                                    rst_i,

    input  logic [N-1:0][DATA_WIDTH-1:0]            act_in,
    input  logic [N-1:0][DATA_WIDTH-1:0]            weight_in,
    input  logic [N-1:0]                            weight_we,
    input  logic [N-1:0]                            buf_sel_in,

    output logic [N-1:0][ACC_WIDTH-1:0]             psum_out
);

    logic [N:0][N-1:0][DATA_WIDTH-1:0] act_chain;
    logic [N:0][N-1:0][DATA_WIDTH-1:0] weight_chain;
    logic [N:0][N-1:0]                 buf_sel_chain;
    logic [N:0][N-1:0]                 weight_we_chain;
    logic [N:0][N-1:0][ACC_WIDTH-1:0]  psum_chain;

    always_comb begin
        for (int col = 0; col < N; col++) begin
            act_chain[0][col]       = act_in[col];
            weight_chain[0][col]    = weight_in[col];
            weight_we_chain[0][col] = weight_we[col];
            buf_sel_chain[0][col]   = buf_sel_in[col];
            psum_chain[0][col]      = '0;
        end
    end

    genvar row, col;
    generate
        for (row = 0; row < N; row++) begin : gen_row
            for (col = 0; col < N; col++) begin : gen_col
                pe #(
                    .DATA_WIDTH(DATA_WIDTH),
                    .ACC_WIDTH(ACC_WIDTH)
                ) pe_inst (
                    .clk_i        (clk_i),
                    .rst_i        (rst_i),
                    .act_in       (act_chain[row][col]),
                    .act_out      (act_chain[row][col+1]),
                    .weight_in    (weight_chain[row][col]),
                    .weight_out   (weight_chain[row+1][col]),
                    .buf_sel_in   (buf_sel_chain[row][col]),
                    .buf_sel_out  (buf_sel_chain[row+1][col]),
                    .weight_we    (weight_we_chain[row][col]),
                    .weight_we_out(weight_we_chain[row+1][col]),
                    .psum_in      (psum_chain[row][col]),
                    .psum_out     (psum_chain[row+1][col])
                );
            end
        end
    endgenerate

    always_comb begin
        for (int col = 0; col < N; col++)
            psum_out[col] = psum_chain[N][col];
    end

endmodule
