module write_transaction #(
    parameter counter_width = 8,
    parameter address_width = 8,
    parameter data_width = 64
) (
    input clk_i,
    input rst_i,

    input [data_width-1:0] data_i,

    input ready_i,
    input valid_i,
    output logic valid_o,
    output logic ready_o,

    input [address_width-1:0] addr_i,
    input [counter_width-1:0] transaction_amount_i,
    input load_valid_i,
    output load_ready_o,

    output logic [address_width-1:0] addr_o,
    output logic [data_width-1:0] data_o
);

    logic [counter_width-1:0] current_count_q, transaction_amount_q, current_count_d;
    logic [address_width-1:0] addr_d;
    logic in_use;

    assign load_ready_o = ~in_use;

    assign valid_o = in_use & valid_i;

    assign ready_o = in_use & ready_i;

    always_comb begin
        data_o = data_i;
    end
    
    always_comb begin
        addr_d = addr_o;
        current_count_d = current_count_q;
        if (valid_o & ready_i & in_use) begin
            current_count_d = current_count_q + 1'b1;
            addr_d = addr_o + 1'b1;
        end
    end

    always_ff @( posedge clk_i ) begin
        if(rst_i) begin
            current_count_q <= '0;
            addr_o <= '0;
            in_use <= '0;
        end else if(load_valid_i & ~in_use) begin
            current_count_q <= '0;
            transaction_amount_q <= transaction_amount_i;
            in_use <= '1; 
            addr_o <= '0;
        end else begin
            current_count_q <= current_count_d;           
            addr_o <= addr_d;

            if (valid_o & ready_i &
                (current_count_d == transaction_amount_q)) begin
                in_use <= 1'b0;
            end
        end
    end
    
endmodule