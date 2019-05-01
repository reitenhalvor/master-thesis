import time
import sys
import math
import numpy as np
import pandas as pd
import scipy.stats as stats
import scipy.integrate as integrate
import pylab

from collections import deque
from matplotlib import pyplot as plt
from anomaly_output import AnomalyOutput
from settings import INPUT_FILE_PATH_TRAIN
from settings import INPUT_FILE_PATH_TEST
from settings import WINDOW_LENGTH
from settings import MIN_NUMBER_OF_RESIDUALS
from settings import DEFAULT_BEST_DIST
from settings import ALPHA
from settings import UPPER_ANOMALY_THRESHOLD
from settings import LOWER_ANOMALY_THRESHOLD
from settings import NUM_AVERAGED_ANOMALY_SCORES
from settings import START

class AnomalyDetection():
    def __init__(self):
        self.residual_distribution = None
        self.predicted = None
        self.actual = None
        self.moving_average_residuals_window = None

        self.read_test_data()
        self.build_residual_distribution()
        self.moving_average_residuals_window = self.calculate_moving_average_residuals(self.residual_distribution)

        self.best_dist = None
        self.dist_params = None
        self.best_dist_string = None
        self.std = None,
        self.mean = None,
        self.residuals = deque(np.zeros(MIN_NUMBER_OF_RESIDUALS), maxlen = MIN_NUMBER_OF_RESIDUALS)
        self.anomaly_scores = deque(np.zeros(MIN_NUMBER_OF_RESIDUALS), maxlen = MIN_NUMBER_OF_RESIDUALS)
        self.anomaly_likelihood = deque(np.zeros(MIN_NUMBER_OF_RESIDUALS) + 0.5, maxlen = MIN_NUMBER_OF_RESIDUALS)
        self.log_anomaly_likelihood = deque(np.zeros(MIN_NUMBER_OF_RESIDUALS) + 0.5, maxlen = MIN_NUMBER_OF_RESIDUALS)

    def __str__(self):
        return (\
                "************************\n" + 
                "AnomalyDetection: \n\n" + 
                "anomaly likelihood: {0:.2f}\n".format(self.anomaly_likelihood[-1]) +
                "log anomaly likelihood: {0:.2f}\n".format(self.log_anomaly_likelihood[-1]) + 
                "anomaly score: {}\n".format(round(self.anomaly_scores[-1], 2)) +
                "mean of res. dist.: {0:.2f}\n".format(np.mean(list(self.moving_average_residuals_window) or 0)) + 
                "std. of res. dist.: {0:.2f}\n".format(np.std(list(self.moving_average_residuals_window) or 0)) + 
                "************************\n"
            )

    
    def build_residual_distribution(self):
        data = pd.read_csv(INPUT_FILE_PATH_TRAIN, sep = ',')
        predicted = data['predicted_train'].values.astype(np.float)
        actual = data['y_train'].values.astype(np.float)
        
        self.residual_distribution = abs(predicted[:MIN_NUMBER_OF_RESIDUALS] - actual[:MIN_NUMBER_OF_RESIDUALS])

    def read_test_data(self):
        data = pd.read_csv(INPUT_FILE_PATH_TEST, sep = ',')
        self.predicted = data['predicted_test'].values.astype(np.float)
        self.actual = data['y_test'].values.astype(np.float)

    def get_moving_average(self, x, N = 10):
        return pd.Series(x).rolling(window=N).mean().iloc[N-1:].values

    def get_best_residual_dist(self):
        self.best_dist = getattr(stats, 'norm')
        self.dist_params = self.best_dist.fit(self.moving_average_residuals_window)

    def calculate_moving_average_residuals(self, x):
        return (
                self.standardize(
                    self.get_moving_average(x = list(x))
            )
        )

    def normality_test(self, x):
        k2, p = stats.normaltest(x)
        alpha = 1e-2
        if (p < alpha):
            print("most likely not normal")
        else:
            print("Most likely normal")
        
    def calculate_anomaly_score(self, residual):
        self.residuals.append(residual)
        
        self.anomaly_scores.append(residual)

        return pd.DataFrame(
                list(self.anomaly_scores)[-NUM_AVERAGED_ANOMALY_SCORES:], 
                columns = ['res']
            ).ewm(alpha = 1).mean()['res'].values[-1]

    def print_anomaly(self, i):
        print("Anomaly detected at index: {}".format(i))
        print(self)

    def tailProbability(self, x):
        self.std = np.std(self.moving_average_residuals_window)
        self.mean = np.mean(self.moving_average_residuals_window)

        z = (x - self.mean) / self.std
        return 1.0 - 0.5 * math.erfc(z / np.sqrt(2))
        
    def calculate_anomaly_likelihood_sg(self, i):
        residual = abs(self.actual[i] - self.predicted[i])
        anomaly_score = self.calculate_anomaly_score(residual)
        
        anomaly_likelihood = self.tailProbability(anomaly_score)
        self.anomaly_likelihood.append(anomaly_likelihood)

        if self.anomaly_likelihood[-1] > UPPER_ANOMALY_THRESHOLD or self.anomaly_likelihood[-1] < LOWER_ANOMALY_THRESHOLD :
            self.print_anomaly(i)


    def standardize(self, x):
        return (x - np.mean(x)) / np.std(x)

def run(anomaly_detection, anomaly_output, plot):
    for i in range(START, len(anomaly_detection.predicted)): 
        anomaly_detection.calculate_anomaly_likelihood_sg(i)

        if i == START:
            anomaly_detection.get_best_residual_dist()

        if plot:
            live_plot(anomaly_detection, anomaly_output, i)


def live_plot(anomaly_detection, anomaly_output, i):
    y = anomaly_detection.actual[(i - WINDOW_LENGTH):i]
    y1 = anomaly_detection.predicted[(i - WINDOW_LENGTH):i]
    x = np.linspace(i - WINDOW_LENGTH, i, WINDOW_LENGTH)

    anomaly_output.update_plot(
        ax = anomaly_output.axs[0],
        x = x,
        y = [y, y1],
        labels = ["Actual", "Predicted"],
        y_lim = (-4, 8),
        x_lim = (i - WINDOW_LENGTH, i)
    )

    y = list(anomaly_detection.anomaly_scores)[-WINDOW_LENGTH:]
    y1 = list(anomaly_detection.anomaly_likelihood)[-WINDOW_LENGTH:]
    y2 = list(anomaly_detection.log_anomaly_likelihood)[-WINDOW_LENGTH:]
    
    anomaly_output.update_plot(
        ax = anomaly_output.axs[2],
        x = x,
        y = [y1],
        labels = ["Anomaly score"],
        y_lim = (0,1),
        x_lim = (i - WINDOW_LENGTH, i)
    )
    anomaly_output.mark_anomalies_in_plot(
        ax = anomaly_output.axs[2],
        y = y1,
        i = i - 1
    )

    if i == START:
        best_dist = anomaly_detection.best_dist
        start = best_dist.ppf(0.01, *anomaly_detection.dist_params)
        stop = best_dist.ppf(0.99, *anomaly_detection.dist_params)
        x = np.linspace(start, stop, WINDOW_LENGTH)
        pdf = anomaly_detection.best_dist.pdf(x, *anomaly_detection.dist_params)

        anomaly_output.axs[1].cla()
        anomaly_output.axs[1].plot(x, pdf, label = "Residuals dist.")
        anomaly_output.axs[1].hist(anomaly_detection.moving_average_residuals_window, bins = 5, density = True)
        anomaly_output.axs[1].legend()

        anomaly_output.axs[3].cla()
        stats.probplot(anomaly_detection.moving_average_residuals_window, dist = 'norm', plot = anomaly_output.axs[3], rvalue = True)
        anomaly_output.axs[3].y_lim=(-10, 10)
        anomaly_output.axs[3].vlines(x = 2.33, ymin = -10, ymax = 10, linestyles='dotted')
        anomaly_output.axs[3].vlines(x = -2.33, ymin = -10, ymax = 10, linestyles='dotted')

def probability_plot(x):
    k, p = stats.normaltest(x)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    res = stats.probplot(x, dist="norm", plot=plt, rvalue=True)
    ax.get_lines()[0].set_markerfacecolor('none')
    ax.get_lines()[0].set_color('black')
    ax.set_ylim((-10, 10))

    ax.get_lines()[1].set_linestyle('dotted')
    ax.get_lines()[1].set_color('black')
    ax.vlines(x = 2.33, ymin = -10, ymax = 10, linestyles='dotted')
    ax.vlines(x = -2.33, ymin = -10, ymax = 10, linestyles='dotted')

    plt.show()


def main(plot):
    anomaly_detection = AnomalyDetection()
    anomaly_output = None

    if plot:
        anomaly_output = AnomalyOutput(positions = [221, 222, 223, 224], figsize = (12, 6)) 
    
    run(
        anomaly_detection = anomaly_detection,
        anomaly_output = anomaly_output,
        plot = plot
    )

if __name__ == "__main__":
    plot = False
    if ('--plot' in sys.argv[1:]):
        plot = True

    main(plot = plot)

