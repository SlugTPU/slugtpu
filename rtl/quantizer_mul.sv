module quantizer_mul #(
    parameter int ACC_WIDTH = 32,
    parameter int FIXED_SHIFT = 16,
    parameter int M0_WIDTH =32 
)(
    input  logic signed [ACC_WIDTH-1:0] psum,
    input  logic signed [M0_WIDTH-1:0] m0,
    output logic signed [7:0]  q_out
);

    logic signed [ACC_WIDTH+M0_WIDTH-1:0] product;
    logic signed [ACC_WIDTH+M0_WIDTH-1:0] rounded;
    logic signed [ACC_WIDTH+M0_WIDTH-1:0] shifted;

    // Multiply
    assign product = psum * m0;

    // Fixed Rounding (effective adds +0.5 to shifted result)
    assign rounded = product + (1 << (FIXED_SHIFT - 1));

    assign shifted = rounded >>> FIXED_SHIFT;

    // Saturation
    always_comb begin
        if (shifted > 127)       q_out = 8'sd127;
        else if (shifted < -128) q_out = -8'sd128;
        else                     q_out = shifted[7:0];
    end
endmodule