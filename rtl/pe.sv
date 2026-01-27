`timescale 1ns/1ps


module pe #(
    parameter int INPUT_WIDTH = 8,
    parameter int WEIGHT_WIDTH = 8,
    parameter int PSUM_WIDTH = INPUT_WIDTH + WEIGHT_WIDTH
) (
    input clk_i,
    input rst_i,

    // North wires of PE
    input logic signed [PSUM_WIDTH - 1:0] pe_psum_i, 
    input logic signed [WEIGHT_WIDTH - 1:0] pe_weight_i,
    input logic [0:0] pe_weight_valid_i,
    
    // West wires of PE
    input logic signed [INPUT_WIDTH - 1:0] pe_input_i, 
    input logic [0:0] pe_input_valid_i,

    // South wires of the PE
    output logic signed [PSUM_WIDTH - 1:0] pe_psum_o,
    output logic signed [WEIGHT_WIDTH - 1:0] pe_weight_o,
    output logic [0:0] pe_weight_valid_o,

    // East wires of the PE
    output logic signed [INPUT_WIDTH - 1:0] pe_input_o,
    output logic [0:0] pe_input_valid_o,
);

    always_ff (@posedge clk_i) begin
        if (rst_i) begin
            pe_psum_o <= '0;
            pe_weight_o <= '0;
            pe_input_o <= '0;
            pe_input_valid_o <= 1'b0;
            pe_weight_valid_o <= 1'b0;
        end
        else begin

            pe_input_valid_o <= pe_input_valid_i;
            pe_weight_valid_o <= pe_weight_valid_i;

            if (pe_input_valid_i && pe_weight_valid_i) begin
                pe_psum_o <= pe_psum_i + (pe_input_i * pe_weight_i); 
            end

            pe_weight_o <= pe_weight_i;
            pe_input_o <= pe_input_i; 
            //In theory, it shouldn't matter if these activate inside or outside the if statement...
        end
    end


endmodule