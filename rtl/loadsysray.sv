`timescale 1ns/1ps

module loadsysray #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH = 32,
    parameter N = 8
)(
    input logic clk_i,
    input logic rst_i,

    //activations
    input logic act_enable,
    input logic act_valid,
    input logic [DATA_WIDTH-1:0] act_i [N],

    //weight
    input logic weight_enable,
    input logic weight_valid,
    input logic [DATA_WIDTH-1:0] weight_i [N],

    output logic [DATA_WIDTH-1:0] psum_out [N] 
);

    genvar k;
    generate
        for (k = 0; k < N; k++) begin
            assign act_sel_n[k]      = act_o[k][DATA_WIDTH+1];
            assign act_valid_n[k]    = act_o[k][DATA_WIDTH];
            assign act_data_n[k]     = act_o[k][DATA_WIDTH-1:0];

            assign weight_sel_n[k]   = weight_o[k][DATA_WIDTH+1];
            assign weight_valid_n[k] = weight_o[k][DATA_WIDTH];
            assign weight_data_n[k]  = weight_o[k][DATA_WIDTH-1:0];
        end
    endgenerate

    //selector bit counter

    reg [$clog2(N)-1:0] count;
    logic select;
    
    always @(posedge clk_i) begin
        if (rst_i) begin
            count <= 0;
            select <= 0;
        end else begin
            if (count == N - 1) begin
                count <= 0;
                select <= ~select;
            end else begin
                count <= count + 1;
            end
        end
    end

    logic [DATA_WIDTH+1:0] act_o [N];
    logic a_valid = act_enable & act_valid;

    tri_shift #(
        .N(N),
        .DATA_W(DATA_WIDTH+2)
    ) activations (
        .clk(clk_i),
        .rst(rst_i),
        .data_i({select, a_valid, act_i}),
        .enable_i(1),
        .data_o(act_o)
    );

    logic [DATA_WIDTH+1:0] weight_o [N];
    logic w_valid = weight_enable & weight_valid;

    tri_shift #(
        .N(N),
        .DATA_W(DATA_WIDTH+2)
    ) weights (
        .clk(clk_i),
        .rst(rst_i),
        .data_i({select, w_valid, weight_i}),
        .enable_i(1),
        .data_o(weight_o)
    );

    logic [DATA_WIDTH-1:0] sys_out [N];


    sysray_nxn #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH(ACC_WIDTH),
        .N(N)
    ) sysray (
        .clk_i(clk_i),
        .rst_i(rst_i),

        .act_valid_n_i(act_valid_n),
        .act_n_i(act_data_n),
        .act_sel_n_i(act_sel_n),

        .weight_valid_n_i(weight_valid_n),
        .weight_n_i(weight_data_n),
        .weight_sel_n_i(weight_sel_n),

        .psum_valid_n_i(1),
        .psum_n_i(0),

        .psum_out_n_o(sys_out),
        .psum_out_valid_n_o()
    );

    logic [ACC_WIDTH-1:0] output_flipped [N];

    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin
            assign output_flipped[i] = sys_out[N-1-i];
        end
    endgenerate
    
    tri_shift #(
        .N(N),
        .DATA_W(ACC_WIDTH)
    ) outputs (
        .clk(clk_i),
        .rst(rst_i),
        .data_i(output_flipped),
        .enable_i(1),
        .data_o(psum_out)        
    );
    
endmodule
