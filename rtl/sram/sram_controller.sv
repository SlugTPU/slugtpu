module sram_controller #(
    parameter data_width = 64,
    parameter addr_width = 8,

    parameter num_readers = 1,
    parameter num_writers = 1
) (
    input clk_i,
    input rst_i,

    // I/O to SRAM module
    output [addr_width-1:0] sram_addr_o,
    output [data_width-1:0] sram_wr_data_o,
    output sram_en_o,
    output sram_rw_mode_o,
    input [data_width-1:0] sram_rd_data_i


);
    
endmodule