class Lead:

    def __init__(self):
        self.state = "under_review"
        self.validations = []

    def recompute(self):

        ok = self.validations.count("approved")
        nok = self.validations.count("rejected")

        if ok >= 2 and nok == 0:
            self.state = "approved"

        elif nok >= 1:
            self.state = "correction"

        else:
            self.state = "under_review"


lead = Lead()

lead.validations.append("approved")
lead.validations.append("approved")

lead.recompute()

print(lead.state)