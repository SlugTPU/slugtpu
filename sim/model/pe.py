class PE:
    def __init__(self, input_width=8, weight_width=8):
        self.INPUT_WIDTH = input_width
        self.WEIGHT_WIDTH = weight_width
        self.PSUM_WEIGHT = input_width + weight_width

        self.pe_psum_o = 0
        self.pe_weight_o = 0
        self.pe_weight_valid_o = 0
        self.pe_input_o = 0
        self.pe_input_valid_i = 0

    def reset(self):
        self.pe_psum_o = 0
        self.pe_weight_o = 0
        self.pe_weight_valid_o = 0
        self.pe_input_o = 0
        self.pe_input_valid_i = 0

    def step(self, pe_psum_i, pe_weight_i, pe_weight_valid_i, pe_input_i, pe_input_valid_i):
        self.pe_weight_valid_o = pe_weight_valid_i;
        self.pe_input_valid_o = pe_input_valid_i;

        if pe_input_valid_i and pe_weight_valid_i:
            self.pe_psum_o = pe_psum_i + (pe_input_i * pe_weight_i)

        self.pe_weight_o = pe_weight_i
        self.pe_input_o = pe_input_i

        return {
            "pe_psum_o": self.pe_psum_o,
            "pe_weight_o": self.pe_weight_o,
            "pe_input_o": self.pe_input_o,
            "pe_weight_valid_o": self.pe_weight_valid_o,
            "pe_input_valid_o": self.pe_input_valid_o
        }
        
        
