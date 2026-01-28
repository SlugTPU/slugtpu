from sim.model.pe import PE

class SystolicArray2x2:
    def __init__(self, input_width=8, weight_width=8):
        self.pe00 = PE(input_width, weight_width)
        self.pe01 = PE(input_width, weight_width)
        self.pe10 = PE(input_width, weight_width)
        self.pe11 = PE(input_width, weight_width)
        
    def reset(self):
        self.pe00.reset()
        self.pe01.reset()
        self.pe10.reset()
        self.pe11.reset()

    def step(self, a_west, a_valid, b_north, b_valid):

        pe00_psum_i = 0
        pe00_weight_i = b_north[0]
        pe00_weight_valid_i = b_valid[0]
        pe00_input_i = a_west[0]
        pe00_input_valid_i = a_valid[0] 
        
        out00 = self.pe00.step(
            pe_psum_i(pe00_psum_i),
            pe_weight_i(pe00_weight_i),
            pe_weight_valid_i(pe00_weight_valid_i),
            pe_input_i(pe00_input_i),
            pe_input_valid_i(pe00_input_valid_i)
        )

        pe01_psum_i = 0
        pe01_weight_i = b_north[1]
        pe01_weight_valid_i = b_valid[1]
        pe01_input_i = out00["pe_input_o"]
        pe01_input_valid_i = out00["pe_valid_input_o"]

        out01 = self.pe01.step(
            pe_psum_i(pe01_psum_i),
            pe_weight_i(pe01_weight_i),
            pe_weight_valid_i(pe01_weight_valid_i),
            pe_input_i(pe01_input_i),
            pe_input_valid_i(pe01_input_valid_i)
        )

        pe10_psum_i = out00["pe_psum_o"]
        pe10_weight_i = out00["pe_weight_o"]
        pe10_weight_valid_i = out00["pe_weight_valid_o"]
        pe10_input_i = a_west[1]
        pe10_input_valid_i = a_valid[1]

        out10 = self.pe10.step(
            pe_psum_i(pe10_psum_i),
            pe_weight_i(pe10_weight_i),
            pe_weight_valid_i(pe10_weight_valid_i),
            pe_input_i(pe10_input_i),
            pe_input_valid_i(pe10_input_valid_i)
        )

        pe11_psum_i = out01["pe_psum_o"]
        pe11_weight_i = out01["pe_weight_o"]
        pe11_weight_valid_i = out01["pe_weight_valid_o"]
        pe11_input_i = out10["pe_input_o"]
        pe11_input_valid_i = out10["pe_input_valid_o"]

        out11 = self.pe11.step(
            pe_psum_i(pe11_psum_i),
            pe_weight_i(pe11_weight_i),
            pe_weight_valid_i(pe11_weight_valid_i),
            pe_input_i(pe11_input_i),
            pe_input_valid_i(pe11_input_valid_i)
        )
        
        return {
            "pe00": out00
            "pe01": out01
            "pe10": out10
            "pe11": out11
        }
