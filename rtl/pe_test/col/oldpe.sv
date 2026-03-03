module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH+1:0] act_in,
    output logic [DATA_WIDTH+1:0] act_out,

    input  logic [DATA_WIDTH+1:0] weight_in,//shift reg chain
    output logic [DATA_WIDTH+1:0] weight_out,

    input  logic weight_valid,
    input  logic weight_sel,

    output logic weight_valid_o,
    output logic weight_sel_o,
    
    input  logic activation_valid,
    input  logic active_sel,

    output logic activation_valid_o,
    output logic active_sel_o,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);
    //double buff
    logic [DATA_WIDTH-1:0] weight_buf [0:1];

    // shift register passes weight data down the column
    always_ff @(posedge clk_i) begin
        if (prevsel != buf_sel)
            weight_out <= weight_in;
 i   end

    // capture into shadow buffer only on broadcast latch
    always_ff @(posedge clk_i) begin
        if (rst_i) begin
            weight_buf[0] <= '0;
            weight_buf[1] <= '0;
        end else if (weight_valid)
            weight_buf[weight_sel] <= weight_in;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[active_sel];

    always_ff @(posedge clk_i) begin
        if (rst_i)
            psum_out <= '0;
      else if (active_valid)
            psum_out <= psum_in + (act_in * active_weight);
    end

    // pass through activation
    always_ff @(posedge clk_i) begin
        act_out <= act_in;
        
        activation_valid_o <= activation_valid;
        active_sel_o <= active_sel;

        weight_valid_o <= weight_valid;
        weight_sel_o <= weight_sel;
    end
endmodule
