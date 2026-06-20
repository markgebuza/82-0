class model:
    def __init__(self, features, output):
        self.features = features
        self.output = output
        self.params = [0] * (len(features) + 1) 

    def pred(self):
        predictions = [self.params[0]] * len(self.output)
        for e in range(0, len(self.output)):
            for f in range(0, len(self.features)):
                predictions[e] += self.params[f + 1] * self.features[f][e]
        return predictions
    
    def pred_new_data(self, data):
        predictions = [self.params[0]] * len(data[0])
        for e in range(0, len(data[0])):
            for f in range(0, len(data)):
                predictions[e] += self.params[f + 1] * data[f][e]
        return predictions


class linear_reg(model):

    def batch_gd(self, alpha= 0.01, max_iters= 5000):
        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)

            predictions = self.pred()

            changelist = [0] * len(self.params)
            for p in range(len(self.params) - 1, -1, -1):
                #print("finding change for parameter "+ str(p))
                step_direction = 0
                for entry in range(0, m):
                    #print("looking at entry " + str(entry))
                    #print("current model predicts output " + str(predictions[entry]) + "\ndiff from actual = " + str(predictions[entry] - self.output[entry]))
                    if p - 1 < 0:
                        step_direction += (predictions[entry] - self.output[entry])
                    else:
                        xj = self.features[p - 1][entry]
                        step_direction += xj * (predictions[entry] - self.output[entry])
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                changelist[p] += step_direction * (alpha / m)

            if all(c * c < 0.0000000000001 for c in changelist):
                return

            for n in range(0, len(self.params)):
                self.params[n] -= changelist[n]

    def stochastic_gd(self, alpha= 0.01, max_iters= 5000):

        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)
            total_change = [0] * len(self.params)
            for entry in range(0, m):
                changelist = [0] * len(self.params)
                #print("looking at entry " + str(entry))
                prediction = self.params[0]
                for f in range(0, len(self.features)):
                    #print("checking feature " + str(f) + " at entry " + str(entry))
                    prediction += self.params[f + 1] * self.features[f][entry]
                for p in range(len(self.params) - 1, -1, -1):
                    step_direction = 0
                    #print("finding change for parameter "+ str(p))
                    #print("current model predicts output " + str(prediction) + "\ndiff from actual = " + str(prediction - self.output[entry]))
                    if p - 1 < 0:
                        xj = 1
                    else:
                        xj = self.features[p - 1][entry]
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                    step_direction = xj * (prediction - self.output[entry]) / m

                    changelist[p] += step_direction * alpha
                for n in range(0, len(self.params)):
                    self.params[n] -= changelist[n]
                    total_change[n] += abs(changelist[n])

            if all(c * c < 0.0000000000001 for c in total_change):
                return

class logistic_reg(model):

    def pred(self):
        predictions = [self.params[0]] * len(self.output)
        for e in range(0, len(self.output)):
            for f in range(0, len(self.features)):
                predictions[e] += self.params[f + 1] * self.features[f][e]
            predictions[e] = 1 / (1 + 2.71828 ** -(predictions[e]))
        return predictions

    def batch_ga(self, alpha= 0.01, max_iters= 5000):
        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)

            predictions = self.pred()

            changelist = [0] * len(self.params)
            for p in range(len(self.params) - 1, -1, -1):
                #print("finding change for parameter "+ str(p))
                step_direction = 0
                for entry in range(0, m):
                    #print("looking at entry " + str(entry))
                    #print("current model predicts output " + str(prediction) + "\ndiff from actual = " + str(prediction - self.output[entry]))
                    if p - 1 < 0:
                        step_direction += (self.output[entry] - predictions[entry])
                    else:
                        xj = self.features[p - 1][entry]
                        step_direction += xj * (self.output[entry] - predictions[entry])
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                changelist[p] += step_direction * (alpha / m)

            if all(c * c < 0.0000000000001 for c in changelist):
                return

            for n in range(0, len(self.params)):
                self.params[n] += changelist[n]

    def stochastic_ga(self, alpha= 0.01, max_iters= 5000):

        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)
            total_change = [0] * len(self.params)
            for entry in range(0, m):
                changelist = [0] * len(self.params)
                #print("looking at entry " + str(entry))
                prediction = self.params[0]
                for f in range(0, len(self.features)):
                    #print("checking feature " + str(f) + " at entry " + str(entry))
                    prediction += self.params[f + 1] * self.features[f][entry]
                for p in range(len(self.params) - 1, -1, -1):
                    step_direction = 0
                    #print("finding change for parameter "+ str(p))
                    #print("current model predicts output " + str(prediction) + "\ndiff from actual = " + str(prediction - self.output[entry]))
                    if p - 1 < 0:
                        xj = 1
                    else:
                        xj = self.features[p - 1][entry]
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                    step_direction += xj * (self.output[entry] - prediction)

                    changelist[p] += step_direction * alpha

                for n in range(0, len(self.params)):
                    self.params[n] += changelist[n]
                    total_change[n] += abs(changelist[n])

            if all(c * c < 0.0000000000001 for c in total_change):
                return

class perceptron(model):

    def pred(self):
        predictions = [self.params[0]] * len(self.output)
        for e in range(0, len(self.output)):
            for f in range(0, len(self.features)):
                predictions[e] += self.params[f + 1] * self.features[f][e]
            predictions[e] = predictions[e] >= 0
        return predictions

    def batch_ga(self, alpha= 0.01, max_iters= 5000):
        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)

            predictions = self.pred()

            changelist = [0] * len(self.params)
            for p in range(len(self.params) - 1, -1, -1):
                #print("finding change for parameter "+ str(p))
                step_direction = 0
                for entry in range(0, m):
                    #print("looking at entry " + str(entry))
                    #print("current model predicts output " + str(prediction) + "\ndiff from actual = " + str(prediction - self.output[entry]))
                    if p - 1 < 0:
                        step_direction += (self.output[entry] - predictions[entry])
                    else:
                        xj = self.features[p - 1][entry]
                        step_direction += xj * (self.output[entry] - predictions[entry])
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                changelist[p] += step_direction * (alpha / m)

            if all(c * c < 0.0000000000001 for c in changelist):
                return

            for n in range(0, len(self.params)):
                self.params[n] += changelist[n]

    def stochastic_ga(self, alpha= 0.01, max_iters= 5000):

        m = len(self.output)
        for i in range(0, max_iters):
            #print("current parameters =", self.params)
            total_change = [0] * len(self.params)
            for entry in range(0, m):
                changelist = [0] * len(self.params)
                #print("looking at entry " + str(entry))
                prediction = self.params[0]
                for f in range(0, len(self.features)):
                    #print("checking feature " + str(f) + " at entry " + str(entry))
                    prediction += self.params[f + 1] * self.features[f][entry]
                for p in range(len(self.params) - 1, -1, -1):
                    step_direction = 0
                    #print("finding change for parameter "+ str(p))
                    #print("current model predicts output " + str(prediction) + "\ndiff from actual = " + str(prediction - self.output[entry]))
                    if p - 1 < 0:
                        xj = 1
                    else:
                        xj = self.features[p - 1][entry]
                    #print("parameter " + str(p) + " value at entry " + str(entry) + " = " + str(xj))
                    step_direction += xj * (self.output[entry] - prediction)

                    changelist[p] += step_direction * alpha

                for n in range(0, len(self.params)):
                    self.params[n] += changelist[n]
                    total_change[n] += abs(changelist[n])

            if all(c * c < 0.0000000000001 for c in total_change):
                return
