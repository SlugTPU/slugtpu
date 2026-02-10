// Multiplies fixed-point input with fixed-point constant scale 

module scale(
    input logic clk_i,
    input logic rst_i,

    input logic signed[31:0] scale_i,
    input logic scale_valid_i,
    input logic data_valid_i,
    input logic signed [31:0] data_i,
    output logic data_valid_o,
    output logic signed [31:0] data_o
);

logic signed [31:0] scale_r;
logic scale_ready_r;

always_ff @(posedge clk_i) begin
    if (rst_i) begin
        scale_r <= '0;
        scale_ready_r <= '0;
    end else if (scale_valid_i) begin
        scale_r <= data_i;
        scale_ready_r <= '0;
    end
end

always_ff @(posedge clk_i) begin
    if (rst_i) begin
        data_o <= 32'b0;
        data_valid_o <= 1'b0;
    end
    else if (data_valid_i &&
            (scale_ready_r || scale_valid_i)) begin
        data_valid_o <= data_valid_i;

        if  (scale_valid_i) begin // bypass path
            data_o <=  data_i * scale_i; 
        end else begin
            data_o <= data_i * scale_r;
        end
    end else begin
        data_valid_o <= '0;
    end
end

endmodule