`timescale 1ns/1ps

module sysray #(
)(
    input logic clk,
    input logic rst,

    input logic [15:0] sysdata11_i,
    input logic [15:0] sysdata12_i,
    
    input logic [15:0] sysweight11_i,
    input logic [15:0] sysweight12_i,

    //
    input logic [1:0] in_valid_input,
    output logic [1:0] out_valid_input,

    input logic [1:0] in_valid_weight,
    output logic [1:0] out_valid_weight
)
    logic pe11_input_valid_o, pe11_weight_valid_o;
    //input for pe12, weight for pe21
    logic pe12_input_vasysweight11_ilid_o, pe12_weight_valid_o;
    //weight for pe 22
    logic pe21_input_valid_o, pe21_weight_valid_o;
    //input for pe 22, weight for column 1 bias
    logic pe22_input_valid_o, pe22_weight_valid_o;
    //weight for column 2 bias

    pe pe11 (
        .clk_i(clk);
        .rst_i(rst);
        .pe_psum_i('0);
        .pe_weight_i();
        .pe_weight_valid_i(in_valid_weight[0]);
        .pe_input_i();
        .pe_input_valid_i(in_valid_input[0]);
        .pe_psum_o();
        .pe_weight_o();
        .pe_weight_valid_o(pe11_input_valid_o);
        .pe_input_o();
        .pe_input_valid_o(pe11_weight_valid_o);
    )

    pe pe12 (
        .clk_i(clk);
        .rst_i(rst);
        .pe_psum_i('0);
        .pe_weight_i();
        .pe_weight_valid_i(in_valid_weight[1]);
        .pe_input_i();
        .pe_input_valid_i(pe11_input_valid_o);
        .pe_psum_o();
        .pe_weight_o();
        .pe_weight_valid_o(pe12_weight_valid_o);
        .pe_input_o();
        .pe_input_valid_o(pe12_input_valid_o);
    )

    pe pe21 (
        .clk_i(clk);
        .rst_i(rst);
        .pe_psum_i();
        .pe_weight_i();
        .pe_weight_valid_i(pe11_weight_valid_o);
        .pe_input_i();
        .pe_input_valid_i(in_valid_input[1]);
        .pe_psum_o();
        .pe_weight_o();
        .pe_weight_valid_o(pe21_weight_valid_o);
        .pe_input_o();
        .pe_input_valid_o(pe21_input_valid_o);
    )

    pe pe22 (
        .clk_i(clk);
        .rst_i(rst);
        .pe_psum_i();
        .pe_weight_i();
        .pe_weight_valid_i(pe12_weight_valid_o);
        .pe_input_i();
        .pe_input_valid_i(pe21_input_valid_o);
        .pe_psum_o();
        .pe_weight_o();
        .pe_weight_valid_o(pe22_weight_valid_o);
        .pe_input_o();
        .pe_input_valid_o(pe22_input_valid_o);
    )


    assign out_valid_input[0] = pe12_input_valid_o;
    assign out_valid_input[1] = pe22_input_valid_o;

    assign out_valid_weight[0] = pe21_weight_valid_o;
    assign out_valid_weight[1] = pe22_weight_valid_o;

endmodule