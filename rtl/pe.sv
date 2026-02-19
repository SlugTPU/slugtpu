module pe #(
    parameter DATA_WIDTH = 8,
    parameter ACC_WIDTH  = 32
)(
    input  logic                  clk_i,
    input  logic                  rst_i,

    input  logic [DATA_WIDTH+1:0] act_in,
    output logic [DATA_WIDTH+1:0] act_out,

    input  logic [DATA_WIDTH+1:0] weight_in,
    output logic [DATA_WIDTH+1:0] weight_out,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    output logic [ACC_WIDTH-1:0]  psum_out
);

    logic sel;
    logic valid;
    logic [DATA_WIDTH-1:0] weight_data;

    assign sel = weight_in[1];
    assign valid = weight_in[0];
    assign weight_data = weight_in[9:2];

    logic [DATA_WIDTH+1:0] weight_buf [0:1];

    always_ff @(posedge clk_i) begin
        if (valid)
            weight_buf[~sel] <= weight_data;
    end

    logic [DATA_WIDTH-1:0] active_weight;
    assign active_weight = weight_buf[sel];

    always_ff @(posedge clk_i) begin
        if (rst_i)
            psum_out <= '0;
        else
            psum_out <= psum_in + (act_in * active_weight);
    end

    logic prev_sel;
    logic [DATA_WIDTH+1:0] prev_weight_in;

    always_ff @(posedge clk_i) begin
        act_out       <= act_in;
        prev_sel      <= sel;
        prev_weight_in <= weight_in;

        if (prev_sel == sel)
            weight_out <= weight_in;
        else
            weight_out <= old_weight_in; 
        
    end

endmodule
