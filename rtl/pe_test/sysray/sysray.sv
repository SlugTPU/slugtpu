module sysray #(
  parameter DATA_WIDTH = 8,
  parameter ACC_WIDTH  = 32
)(
  input logic clk_i,
  input logic rst_i,

  input logic [DATA_WIDTH:0] act0,
  input logic [DATA_WIDTH:0] act1,

  input logic [DATA_WIDTH:0] weight0,
  input logic [DATA_WIDTH:0] weight1,

  input logic weight_valid0,
  input logic weight_valid1,

  input logic act_valid0,
  input logic act_valid1,

  output psum_out1,
  output psum_out2
);

  logic [DATA_WIDTH:0]  act00_out;
  logic [DATA_WIDTH:0]  weight00_out;
  logic                 weight_valid00_out;
  logic                 act_valid00_out;
  logic [ACC_WIDTH-1:0] psum_00_out              

  pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) pe00 (
    .clk_i(clk_i),
    .rst_i(rst_i),
    .act_in(act0_in),
    .act_out(act00_out),
    .weight_in(weight0),
    .weight_out(weight00_out),
    .weight_valid(weight_valid0),
    .weight_valid_o(weight_valid00_out),
    .act_valid(act_valid0),
    .act_valid_o(act_valid00_out),
    .psum_in(),
    .psum_out(psum_00_out)
  );

  logic [DATA_WIDTH:0]  weight01_out;
  logic                 weight_valid01_out;
  logic [ACC_WIDTH-1:0] psum_01_out

  pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) pe01 (
    .clk_i(clk_i),
    .rst_i(rst_i),
    .act_in(act00_out),
    .act_out(),
    .weight_in(weight1),
    .weight_out(weight01_out),
    .weight_valid(weight_valid1),
    .weight_valid_o(weight_valid01_out),
    .act_valid(act_valid00_out),
    .act_valid_o(),
    .psum_in(),
    .psum(psum_01_out)
  );

  logic [DATA:WIDTH:0]  act_10_out;
  logic                 act_valid10_out;
  logic [ACC_WIDTH-1:0] psum_10_out;

  pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) pe10 (
    .clk_i(clk_i),
    .rst_i(rst_i),
    .act_in(act1),
    .act_out(act_10_out),
    .weight_in(weight00_out),
    .weight_out()
    .weight_valid(weight_valid00_out),
    .weight_valid_o()
    .act_valid(act_valid1),
    .act_valid_o(act_valid10_out),
    .psum_in(psum_00_out),
    .psum_out(psum_10_out)
  );

  logic [ACC_WIDTH-1:0] psum_11_out;

  pe #(.DATA_WIDTH(DATA_WIDTH), .ACC_WIDTH(ACC_WIDTH)) pe11 (
    .clk_i(clk_i),
    .rst_i(rst_i),
    .act_in(act_10_out),
    .act_out(),
    .weight_in(weight01_out),
    .weight_out(),
    .weight_valid(weight_valid01_out),
    .weight_valid_o(),
    .act_valid(act_valid10_out),
    .act_valid_o()
    .psum_in(psum_01_out),
    .psum_out(psum_11_out)
  ); 
     
  
