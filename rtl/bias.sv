`timescale 1ns/1ps

module bias(
    input logic clk_i,
    input logic rst_i,

    input logic signed[15:0] bias_i,
    input logic valid_i,
    input logic signed [15:0] data_i,
    output logic valid_o;
    output logic signed [15:0] data_o
);

always @(posedge clk_i) begin
    if (rst_i) begin
        data_o <= 16'b0;
        valid_o <= 1'b0;
    end
    else if (valid_i) begin 
        valid_o <= valid_i;
        data_o <= bias_i + data_i; 
    end
end

endmodule