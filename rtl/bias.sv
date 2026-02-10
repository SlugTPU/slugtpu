module bias(
    input logic clk_i,
    input logic rst_i,

    input logic signed[31:0] bias_i,
    input logic bias_valid_i,
    input logic data_valid_i,
    input logic signed [31:0] data_i,
    output logic data_valid_o,
    output logic signed [31:0] data_o
);

logic signed [31:0] bias_r;
logic bias_ready_r;

always_ff @(posedge clk_i) begin
    if (rst_i) begin
        bias_r <= '0;
        bias_ready_r <= '0;
    end else if (bias_valid_i) begin
        bias_r <= data_i;
        bias_ready_r <= '0;
    end
end

always_ff @(posedge clk_i) begin
    if (rst_i) begin
        data_o <= 32'b0;
        data_valid_o <= 1'b0;
    end
    else if (data_valid_i &&
            (bias_ready_r || bias_valid_i)) begin
        data_valid_o <= data_valid_i;

        if (bias_valid_i) begin // bypass path
            data_o <=  data_i + bias_i; 
        end else begin
            data_o <= data_i + bias_r;
        end
    end else begin
        data_valid_o <= '0;
    end
end

endmodule