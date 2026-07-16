from agents.identity_agent import identify_caller

class ROIAgent:
    def __init__(self):
        pass
    def verify(self, transcript):
        return identify_caller(transcript)
