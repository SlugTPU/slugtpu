`timescale 1ns/1ps
`default_nettype none

module spi_slave (
    input  wire clk,
    input  wire rst,

    input  wire sclk,
    input  wire mosi,
    input  wire cs_n,
    output wire miso,

    output reg  [7:0] rx_data,
    output reg        rx_valid,

    input  wire [7:0] tx_data,
    input  wire       tx_valid
);

    reg [7:0] shift_rx;
    reg [7:0] shift_tx;
    reg [2:0] bit_cnt;

    reg sclk_d;
    wire sclk_rise;

    assign sclk_rise = (sclk == 1'b1) && (sclk_d == 1'b0);
    assign miso = shift_tx[7];

    always @(posedge clk) begin
        sclk_d <= sclk;
    end

    always @(posedge clk) begin
        if (rst) begin
            bit_cnt  <= 3'd0;
            shift_rx <= 8'd0;
            shift_tx <= 8'd0;
            rx_valid <= 1'b0;
        end
        else begin
            rx_valid <= 1'b0;

            if (cs_n) begin
                bit_cnt <= 3'd0;
            end
            else if (sclk_rise) begin
                shift_rx <= {shift_rx[6:0], mosi};
                shift_tx <= {shift_tx[6:0], 1'b0};

                if (bit_cnt == 3'd7) begin
                    rx_data  <= {shift_rx[6:0], mosi};
                    rx_valid <= 1'b1;
                    bit_cnt  <= 3'd0;

                    // Loads NEXT byte to be shifted out
                    if (tx_valid)
                        shift_tx <= tx_data;
                end
                else begin
                    bit_cnt <= bit_cnt + 3'd1;
                end
            end
        end
    end

endmodule

`default_nettype wire
