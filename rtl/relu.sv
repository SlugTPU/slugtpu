module relu(
    input logic clk_i,
    input logic rst_i,

    input logic data_valid_i,
    input logic signed [31:0] data_i,
    output logic data_valid_o,
    output logic signed [31:0] data_o
);

always_ff @(posedge clk_i) begin
    if (rst_i) begin
        data_o <= '0;
        data_valid_o <= 1'b0;
    end else begin
        data_valid_o <= data_valid_i;
        data_o <= (data_i[31]) ? 32'sd0 : data_i;
    end
end

endmodule