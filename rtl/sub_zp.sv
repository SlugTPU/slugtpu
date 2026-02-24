module sub_zp(
    input logic clk_i,
    input logic rst_i,

    input logic signed [31:0] zp_i,
    input logic zp_valid_i,

    input logic data_valid_i,
    input logic signed [31:0] data_i,
    output logic data_valid_o,
    output logic signed [31:0] data_o
);

    logic signed [31:0] zp_q;
    logic zp_loaded_q;

    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            zp_q <= '0;
            zp_loaded_q <= 1'b0;
        end else if (zp_valid_i) begin
            zp_q <= zp_i;
            zp_loaded_q <= 1'b1;
        end
    end

    //pipeline next state
    logic signed [31:0] zp_active;
    logic pipe_valid_d;
    logic signed [31:o] pipe_data_d;

    always_comb begin
        zp_active = (zp_valid_i) ? zp_i : zp_q;

        pipe_valid_d = data_valid_i & (zp_loaded_q | zp_valid_i);
        pipe_data_d = data_i - zp_active;
    end

    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            data_o <= '0;
            data_valid_o <= 1'b0;
        end else begin
            data_valid_o <= pipe_valid_d;
            data_o <= pipe_data_d;
        end
    end

endmodule
