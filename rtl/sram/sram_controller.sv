module sram_mux #(
    parameter data_width = 64,
    parameter addr_width = 8,

    parameter num_readers = 1,
    parameter num_writers = 1
) (
    input clk_i,
    input rst_i,

    // IO to SRAM module
    output [addr_width-1:0] sram_addr_o,
    output [data_width-1:0] sram_wr_data_o,
    output sram_en_o,
    output sram_rw_mode_o,
    input [data_width-1:0] sram_rd_data_i,

    // IO to mem_transaction modules in write mode
    input [num_writers-1:0] wr_valid_i,
    output [num_writers-1:0] wr_ready_o,
    input [addr_width-1:0] wr_addr_i [num_writers-1:0],
    input [data_width-1:0] unified_write_buffer_i,

    // IO to mem_transaction modules in read mode
    input [num_readers-1:0] rd_ready_i,
    output [num_readers-1:0] rd_valid_o,
    input [addr_width-1:0] rd_addr_i [num_readers-1:0],
    output [data_width-1:0] unified_read_buffer_o
);

    logic rw_mode;
    logic in_use;
    logic [num_readers-1:0] which_reader;
    logic [num_writers-1:0] which_writer;

    assign rd_valid_o = which_reader;
    assign wr_ready_o = which_writer;
    assign unified_read_buffer_o = sram_rd_data_i;
    assign sram_wr_data_o = unified_write_buffer_i;

    always_ff @( posedge clk_i ) begin
        if(rst_i) begin
            which_reader <= '1;
            which_writer <= '1;
            rw_mode <= '0;
            in_use <= '0;
        end else if(~in_use & |which_reader ) begin
            
        end
    end

    
endmodule
