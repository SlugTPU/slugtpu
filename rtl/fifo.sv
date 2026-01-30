module fifo #(
    parameter DEPTH_P = 7,
    parameter WIDTH_P = 8
) (
    input clk_i,
    input rst_i,

    // data
    input logic [WIDTH_P - 1:0] data_i,
    output logic [WIDTH_P - 1:0] data_o,
    // handshake
    input logic [0:0] valid_i,
    input logic [0:0] ready_i,
    output logic [0:0] valid_o,
    output logic [0:0] ready_o
);
    localparam depth_log2_p = $clog2(DEPTH_P);

    logic [WIDTH_P - 1:0] mem [DEPTH_P];
    logic [depth_log2_p:0]    wr_ptr_n, wr_ptr_q, rd_ptr_n, rd_ptr_q;
    logic [0:0]               write_en_w, read_en_w;
    wire  [0:0]               is_full_w, is_empty_w;

    assign read_en_w = (ready_i && valid_o);
    assign write_en_w = (valid_i && ready_o);

    assign rd_ptr_n = (read_en_w) ? rd_ptr_q + 1 : rd_ptr_q;
    assign wr_ptr_n = (write_en_w) ? wr_ptr_q + 1 : wr_ptr_q;

    generate
    if (DEPTH_P > 1) begin: is_full_empty_deep
        assign is_full_w = (wr_ptr_q[depth_log2_p] != rd_ptr_q[depth_log2_p]) &&
                           (wr_ptr_q[depth_log2_p - 1:0] == rd_ptr_q[depth_log2_p - 1:0]);
        assign is_empty_w = wr_ptr_q == rd_ptr_q;
    end else begin: is_full_empty_shallow
       assign is_full_w = (wr_ptr_q != rd_ptr_q);
       assign is_empty_w = (wr_ptr_q == rd_ptr_q);
    end
    endgenerate

   assign ready_o = ~is_full_w;
   assign valid_o = ~is_empty_w;

    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            wr_ptr_q <= '0;
            rd_ptr_q <= '0;
        end else begin
            wr_ptr_q <= wr_ptr_n;
            rd_ptr_q <= rd_ptr_n;
        end
    end

    generate
    if (DEPTH_P > 1) begin: data_rw_deep
        always_ff @(posedge clk_i) begin
            if (write_en_w) begin
                mem[wr_ptr_q[depth_log2_p - 1:0]] <= data_i;
            end
            if (read_en_w) begin
                data_o <= mem[rd_ptr_q[depth_log2_p - 1:0]];
            end
        end
    end else begin: data_rw_shallow
        always_ff @(posedge clk_i) begin
            if (write_en_w) begin
                mem[0] <= data_i;
            end
            if (read_en_w) begin
                data_o <= mem[0];
            end
        end
    end
    endgenerate

endmodule
