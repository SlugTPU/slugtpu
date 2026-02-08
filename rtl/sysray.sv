`timescale 1ns/1ps

module sysray #(
    parameter int N       = 2,   
    parameter int DATA_W  = 16,  
    parameter int PSUM_W  = 32  
)(
    input  logic                   clk,
    input  logic                   rst,

    input  logic [DATA_W-1:0]      sysdata_i   [N],

    input  logic [DATA_W-1:0]      sysweight_i [N],

    input  logic [N-1:0]           in_valid_input,   
    input  logic [N-1:0]           in_valid_weight,  

    output logic [N-1:0]           out_valid_input,  
    output logic [N-1:0]           out_valid_weight  
);

    logic [DATA_W-1:0]  pe_input_data   [N][N];
    logic [DATA_W-1:0]  pe_weight_data  [N][N];
    logic [PSUM_W-1:0]  pe_psum         [N][N];

    logic               input_valid     [N][N];
    logic               weight_valid    [N][N];

    genvar i, j;
    generate
        for (i = 0; i < N; i++) begin : ROW
            for (j = 0; j < N; j++) begin : COLUMN

                logic [DATA_W-1:0]  pe_input_i;
                logic [DATA_W-1:0]  pe_weight_i;
                logic [PSUM_W-1:0]  pe_psum_i;
                logic               pe_input_valid_i;
                logic               pe_weight_valid_i;

                if (j == 0) begin
                    assign pe_input_i       = sysdata_i[i];
                    assign pe_input_valid_i = in_valid_input[i];
                end
                else begin
                    assign pe_input_i       = pe_input_data[i][j-1];
                    assign pe_input_valid_i = input_valid[i][j-1];
                end

                if (i == 0) begin
                    assign pe_weight_i       = sysweight_i[j];
                    assign pe_weight_valid_i = in_valid_weight[j];
                end
                else begin
                    assign pe_weight_i       = pe_weight_data[i-1][j];
                    assign pe_weight_valid_i = weight_valid[i-1][j];
                end

                if (i == 0) begin
                    assign pe_psum_i = '0;  
                end
                else begin
                    assign pe_psum_i = pe_psum[i-1][j];
                end

                pe #(
                    .DATA_W (DATA_W),
                    .PSUM_W (PSUM_W)
                ) u_pe (
                    .clk_i             (clk),
                    .rst_i             (rst),

                    .pe_input_i        (pe_input_i),
                    .pe_weight_i       (pe_weight_i),
                    .pe_input_valid_i  (pe_input_valid_i),
                    .pe_weight_valid_i (pe_weight_valid_i),
                    .pe_psum_i         (pe_psum_i),

                    .pe_input_o        (pe_input_data[i][j]),
                    .pe_weight_o       (pe_weight_data[i][j]),
                    .pe_input_valid_o  (input_valid[i][j]),
                    .pe_weight_valid_o (weight_valid[i][j]),
                    .pe_psum_o         (pe_psum[i][j])
                );

            end
        end
    endgenerate

    generate
        for (i = 0; i < N; i++) begin : 
            assign out_valid_input[i] = input_valid[i][N-1];
        end

        for (j = 0; j < N; j++) begin : 
            assign out_valid_weight[j] = weight_valid[N-1][j];
        end
    endgenerate

endmodule
