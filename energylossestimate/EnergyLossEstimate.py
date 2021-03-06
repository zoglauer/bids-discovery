###################################################################################################
#
# EnergyLossEstimate.py
#
# Copyright (C) by Andreas Zoglauer, Rithwik Sudharsan, Anna Shang, Amal Metha & Caitlyn Chen.
# All rights reserved.
#
# Please see the file License.txt in the main repository for the copyright-notice.
#
###################################################################################################




###################################################################################################


import ROOT
import array
import os
import sys
import random
import time
import collections
import numpy as np
import math, datetime
from tqdm import tqdm

import pickle
from voxnet import *
from volumetric_data import ShapeNet40Vox30

import matplotlib.pyplot as plt
from matplotlib import colors
from matplotlib.ticker import PercentFormatter

from sklearn.metrics import mean_squared_error

# Fixing random state for reproducibility
np.random.seed(19680801)

tf.compat.v1.disable_eager_execution() # Disable v2 eager execution.
###################################################################################################
class EnergyLossEstimate:
  """
  This class performs energy loss training. A typical usage would look like this:

  AI = EnergyLossEstimate("Ling2.seq3.quality.root", "Results", "TF:VOXNET", 1000000)
  AI.train()
  AI.test()

  """


###################################################################################################


  def __init__(self, FileName, Output, Algorithm, MaxEvents):
    """
    The default constructor for class EventClustering

    Attributes
    ----------
    FileName : string
      Data file name (something like: X.maxhits2.eventclusterizer.root)
    OutputPrefix: string
      Output filename prefix as well as outout directory name
    Algorithms: string
      The algorithms used during training. Seperate multiples by commma (e.g. "MLP,DNNCPU")
    MaxEvents: integer
      The maximum amount of events to use

    """

    self.FileName = FileName
    self.Output = 'Results'
    if Output != '':
      self.Output = self.Output + '_' + Output
    self.Algorithms = Algorithm
    self.MaxEvents = MaxEvents

    self.EventTypes = []
    self.EventHits = []
    self.EventEnergies = []
    
    self.EventTypesTrain = []
    self.EventTypesTest = []

    self.EventHitsTrain = []
    self.EventHitsTest = []

    self.EventEnergiesTrain = []
    self.EventEnergiesTest = []
    
    
    self.LastEventIndex = 0
    
    self.BatchSize = 20
    self.XBins = 110
    self.YBins = 110
    self.ZBins = 48
    self.MaxLabel = 0

    #might have to tune these values
    self.XMin = -55
    self.XMax = 55

    self.YMin = -55
    self.YMax = 55

    self.ZMin = 0
    self.ZMax = 48
    
    #keras model development
    self.OutputDirectory = "output.txt"
    self.train_test_split = 0.9
    self.keras_model = None

    self.DataLoaded = False


###################################################################################################


  def train(self):
    """
    Switch between the various machine-learning libraries based on self.Algorithm
    """
    if self.Algorithms.startswith("TF:"):
        model = tfModel(self)
        model.trainTFMethods()
    elif self.Algorithms == "median":
        x = [500+100*i for i in range(6)]
        losses = []
        for numBins in x:
            model = medianModel(self, numBins=numBins)
            losses.append(model.loss())
        best = min(losses)
        print("Best parameters: (Best MSE, Best numBins)")
        print(best, x[losses.index(best)])

    return

  def test(self):
    """
    Switch between the various machine-learning libraries based on self.Algorithm
    """
    if self.Algorithms == "median":
      model = medianModel(self, numBins=100)
      print("Median Model MSE: {}".format(model.loss()))

    return


###################################################################################################


  def loadData(self):
    """
    Prepare numpy array datasets for scikit-learn and tensorflow models
    
    Returns:
      list: list of the events types in numerical form: 1x: Compton event, 2x pair event, with x the detector (0: passive material, 1: tracker, 2: absober)
      list: list of all hits as a numpy array containing (x, y, z, energy) as row 
    """
   
    print("{}: Load data from sim file".format(time.time()))


    import ROOT as M

    # Load MEGAlib into ROOT
    M.gSystem.Load("$(MEGALIB)/lib/libMEGAlib.so")

    # Initialize MEGAlib
    G = M.MGlobal()
    G.Initialize()
    
    # Fixed for the time being
    GeometryName = "$(MEGALIB)/resource/examples/geomega/GRIPS/GRIPS_extended.geo.setup"

    # Load geometry:
    Geometry = M.MDGeometryQuest()
    if Geometry.ScanSetupFile(M.MString(GeometryName)) == True:
      print("Geometry " + GeometryName + " loaded!")
    else:
      print("Unable to load geometry " + GeometryName + " - Aborting!")
      quit()
    

    Reader = M.MFileEventsSim(Geometry)
    if Reader.Open(M.MString(self.FileName)) == False:
      print("Unable to open file " + FileName + ". Aborting!")
      quit()

    #Hist = M.TH2D("Energy", "Energy", 100, 0, 600, 100, 0, 600)
    #Hist.SetXTitle("Input energy [keV]")
    #Hist.SetYTitle("Measured energy [keV]")


    EventTypes = []
    EventHits = []
    EventEnergies = []
    GammaEnergies = []
    PairEvents = []

    NEvents = 0
    while True: 
      print("   > {} Events Processed...".format(NEvents), end='\r')

      Event = Reader.GetNextEvent()
      if not Event:
        break
  
      Type = 0
      if Event.GetNIAs() > 0:
        #Second IA is "PAIR" (GetProcess) in detector 1 (GetDetectorType()
        GammaEnergies.append(Event.GetIAAt(0).GetSecondaryEnergy())
        if Event.GetIAAt(1).GetProcess() == M.MString("COMP"):
          Type += 0 + Event.GetIAAt(1).GetDetectorType()
        elif Event.GetIAAt(1).GetProcess() == M.MString("PAIR"):
          Type += 10 + Event.GetIAAt(1).GetDetectorType()
      else:
        break
      
      if Type+1 > self.MaxLabel:
        self.MaxLabel = Type +1
  
      TotalEnergy = 0
      Hits = np.zeros((Event.GetNHTs(), 4))
      for i in range(0, Event.GetNHTs()):
        Hits[i, 0] = Event.GetHTAt(i).GetPosition().X()
        Hits[i, 1] = Event.GetHTAt(i).GetPosition().Y()
        Hits[i, 2] = Event.GetHTAt(i).GetPosition().Z()
        hitEnergy = Event.GetHTAt(i).GetEnergy()
        Hits[i, 3] = hitEnergy
        TotalEnergy += hitEnergy
      
      NEvents += 1
      EventTypes.append(Type)
      EventHits.append(Hits)
      EventEnergies.append(TotalEnergy)
      
      if NEvents >= self.MaxEvents:
        break
  
    print("Occurances of different event types:")
    print(collections.Counter(EventTypes))
    
    import math

    self.LastEventIndex = 0
    self.EventHits = EventHits
    self.EventTypes = EventTypes 
    self.EventEnergies = EventEnergies
    self.GammaEnergies = GammaEnergies

    with open('EventEnergies.data', 'wb') as filehandle:
      pickle.dump(self.EventEnergies, filehandle)
    with open('GammaEnergies.data', 'wb') as filehandle:
      pickle.dump(self.GammaEnergies, filehandle)
     
    ceil = math.ceil(len(self.EventHits)*0.75)
    self.EventTypesTrain = self.EventTypes[:ceil]
    self.EventTypesTest = self.EventTypes[ceil:]
    self.EventHitsTrain = self.EventHits[:ceil]
    self.EventHitsTest = self.EventHits[ceil:]
    self.EventEnergiesTrain = self.EventEnergies[:ceil]
    self.EventEnergiesTest = self.EventEnergies[ceil:]

    self.NEvents = NEvents

    self.DataLoaded = True

    return 
  
  def getEnergies(self):
    if os.path.exists('EventEnergies.data') and os.path.exists('GammaEnergies.data'):
      with open('EventEnergies.data', 'rb') as filehandle:
        EventEnergies = pickle.load(filehandle)
      with open('GammaEnergies.data', 'rb') as filehandle:
        GammaEnergies = pickle.load(filehandle)
      print(len(EventEnergies), len(GammaEnergies))
      if len(EventEnergies) == len(GammaEnergies) >= self.MaxEvents:
        return EventEnergies[:self.MaxEvents], GammaEnergies[:self.MaxEvents]

    if not self.DataLoaded:
      self.loadData()
    return self.EventEnergies, self.GammaEnergies


###################################################################################################


class medianModel:
  def __init__(self, dataLoader: EnergyLossEstimate, numBins=None):
    self.dataLoader = dataLoader
    self.medians = None
    if numBins == None:
      self.numBins = 100 #self.dataLoader.MaxEvents//50
    else:
      self.numBins = numBins
  
    x, y = self.dataLoader.getEnergies()
    print(len(x), len(y))
    h, xbins, ybins, _ = plt.hist2d(x, y, bins=self.numBins, norm=colors.LogNorm())
    plt.clf()
    
    ("Loading Median Model... {} bins".format(self.numBins))

    x_medians = []
    y_medians = []
    y_errors = []
    for i in tqdm(range(len(xbins) - 1)):
      data = []
      binStart, binEnd = xbins[i], xbins[i+1]
      for j in range(len(x)):
        xVal, yVal = x[j], y[j]
        if binStart <= xVal <= binEnd:
          data.append(yVal)
      if len(data) > 0:
        x_medians.append(binStart)
        y_medians.append(np.median(data))
        y_errors.append(np.std(data))
      
    self.medians = x_medians, y_medians, y_errors
    self.binWidth = xbins[1] - xbins[0]
    self.x, self.y = x, y

  def predict(self, detectedEnergy):
    y_medians = self.medians[1]
    whichBin = int(detectedEnergy // self.binWidth)
    if whichBin >= len(y_medians):
      whichBin = len(y_medians) - 1
    return y_medians[whichBin]
    
  def loss(self):
    x, y = self.x, self.y
    predictions = [self.predict(detected) for detected in x]
    ret = mean_squared_error(predictions, y)
    print("MSE: {}".format(ret))
    return ret

  def plotHist(self):
    plt.clf()
    x, y = self.x, self.y
    print(len(x), len(y))
    plt.hist2d(x, y, self.numBins, norm=colors.LogNorm())
    plt.xlabel("Measured Total Hit Energy (keV)")
    plt.ylabel("True Gamma Energy (keV)")
    #plt.show()
    file = 'estimateHist.png'
    plt.savefig(file, format="PNG")
    print("Histogram Plotted!")

  def plotMedians(self):
    plt.clf()
    x_medians, y_medians, y_errors = self.medians
    plt.errorbar(x_medians, y_medians, yerr=y_errors, markersize=0.5, elinewidth=0.3)
    
    plt.xlabel("Measured Total Hit Energy (keV)")
    plt.ylabel("Median Gamma Energy (keV)")
    file = 'estimateMedian.png'
    plt.savefig(file, format="PNG")
    print("Medians Plotted!")


  
  

  '''
  def plotScatter(self):
    if not self.dataLoader.DataLoaded:
      self.dataLoader.loadData()
    plt.clf()
    plt.scatter(self.dataLoader.EventEnergies, self.dataLoader.GammaEnergies, s=1e-5)
    print(len(self.dataLoader.EventEnergies), len(self.dataLoader.GammaEnergies))
    plt.xlabel('Measured Energies')
    plt.ylabel('True Energies')
    file = 'estimateScatter.png'
    plt.savefig(file, format="PNG")
    print("Scatterplot Plotted!")
  '''



###################################################################################################
class tfModel:
  def __init__(self, dataLoader: EnergyLossEstimate):
    self.dataLoader = dataLoader

  def trainTFMethods(self):
 
    print("Starting training...")
 
    # Load the data
    #eventtypes: what we want to train {21:11, }
    #EventHits: what to conver to the point cloud
    #numpy array
    self.dataLoader.loadData()

    # Add VoxNet here

    print("Initializing voxnet")

    voxnet = VoxNet(self.dataLoader.BatchSize, self.dataLoader.XBins, self.dataLoader.YBins, self.dataLoader.ZBins, self.dataLoader.MaxLabel)
    #batch_size = 1

    p = dict() # placeholders

    p['labels'] = tf.placeholder(tf.float32, [None, self.dataLoader.MaxLabel])
    p['loss'] = tf.nn.softmax_cross_entropy_with_logits(logits=voxnet[-2], labels=p['labels'])
    p['loss'] = tf.reduce_mean(p['loss']) 
    p['l2_loss'] = tf.add_n([tf.nn.l2_loss(w) for w in voxnet.kernels]) 
    p['correct_prediction'] = tf.equal(tf.argmax(voxnet[-1], 1), tf.argmax(p['labels'], 1))
    p['accuracy'] = tf.reduce_mean(tf.cast(p['correct_prediction'], tf.float32))
    p['learning_rate'] = tf.placeholder(tf.float32)
    with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
      p['train'] = tf.train.AdamOptimizer(p['learning_rate'], epsilon=1e-3).minimize(p['loss'])
    p['weights_decay'] = tf.train.GradientDescentOptimizer(p['learning_rate']).minimize(p['l2_loss'])

    # Hyperparameters
    num_batches = 2147483647
    #batch_size = 50

    initial_learning_rate = 0.001
    min_learning_rate = 0.000001
    learning_rate_decay_limit = 0.0001

    #TODO://
    #not sure what supposed to go inside len
    num_batches_per_epoch = len(self.dataLoader.EventTypesTrain) / float(self.dataLoader.BatchSize)
    learning_decay = 10 * num_batches_per_epoch
    weights_decay_after = 5 * num_batches_per_epoch

    checkpoint_num = 0
    learning_step = 0
    min_loss = 1e308
    test_accuracy_baseline = 0


    print("Creating check points directory")
    if not os.path.isdir(self.dataLoader.Output):
      os.mkdir(self.dataLoader.Output)

    with open(self.dataLoader.Output + '/accuracies.txt', 'w') as f:
      f.write('')

    with open(self.dataLoader.Output + '/accuracies_labels.txt', 'w') as f:
      f.write('')

    with tf.Session() as session:
      print("Initializing global TF variables")
      session.run(tf.global_variables_initializer())
      
      for batch_index in range(num_batches):
        print("Iteration {0}".format(batch_index+1))
        
        learning_rate = max(min_learning_rate, initial_learning_rate * 0.5**(learning_step / learning_decay))
        learning_step += 1

        if batch_index > weights_decay_after and batch_index % 256 == 0:
          session.run(p['weights_decay'], feed_dict=feed_dict)

        voxs, labels = self.dataLoader.get_batch(self.dataLoader.BatchSize, True)

        tf.logging.set_verbosity(tf.logging.DEBUG)
        
        print("Starting training run")
        start = time.time()
        feed_dict = {voxnet[0]: voxs, p['labels']: labels, p['learning_rate']: learning_rate, voxnet.training: True}
        session.run(p['train'], feed_dict=feed_dict)
        print("Done with training run after {0} seconds".format(round(time.time() - start, 2)))

        if batch_index and batch_index % 8 == 0:
          print("{} batch: {}".format(datetime.datetime.now(), batch_index))
          print('learning rate: {}'.format(learning_rate))

          feed_dict[voxnet.training] = False
          loss = session.run(p['loss'], feed_dict=feed_dict)
          print('loss: {}'.format(loss))

          if (batch_index and loss > 1.5 * min_loss and learning_rate > learning_rate_decay_limit): 
            min_loss = loss
            learning_step *= 1.2
            print("decreasing learning rate...")
          min_loss = min(loss, min_loss)


        if batch_index and batch_index % 100 == 0:

          num_accuracy_batches = 30
          total_accuracy = 0
          for x in range(num_accuracy_batches):
            #TODO://
            #replace with actual data
            voxs, labels = self.dataLoader.get_batch(self.dataLoader.BatchSize, True)
            feed_dict = {voxnet[0]: voxs, p['labels']: labels, voxnet.training: False}
            total_accuracy += session.run(p['accuracy'], feed_dict=feed_dict)
          training_accuracy = total_accuracy / num_accuracy_batches
          print('training accuracy: {}'.format(training_accuracy))

          num_accuracy_batches = 90
          total_accuracy = 0
          for x in range(num_accuracy_batches):
            voxs, labels = self.dataLoader.get_batch(self.dataLoader.BatchSize, True)
            feed_dict = {voxnet[0]: voxs, p['labels']: labels, voxnet.training: False}
            total_accuracy += session.run(p['accuracy'], feed_dict=feed_dict)
          test_accuracy = total_accuracy / num_accuracy_batches
          print('test accuracy: {}'.format(test_accuracy))

          num_accuracy_batches = 90
          total_correct = []
          total_wrong = []
          for x in range(num_accuracy_batches):
            voxs, labels = self.dataLoader.get_batch(self.dataLoader.BatchSize, True)
            feed_dict = {voxnet[0]: voxs, p['labels']: labels, voxnet.training: False}
            correct_prediction = session.run(p['correct_prediction'], feed_dict=feed_dict)
            for i in range(len(correct_prediction)):
              if (correct_prediction[i] == 1):
                total_correct.append(labels[i])
              else:
                total_wrong.append(labels[i])
          sum_total_correct = sum(total_correct)
          sum_total_wrong = sum(total_wrong)
          for i in range(len(sum_total_correct)):
            if (sum_total_correct[i] == 0):
              if (sum_total_wrong[i] == 0):
                sum_total_correct[i] = 1
                sum_total_wrong[i] = -2
          test_accuracy_labels = sum_total_correct/ (sum_total_correct + sum_total_wrong)
          print('test accuracy of labels: {}'.format(test_accuracy_labels))

          # test_accuracy_labels_pos = [x for x in test_accuracy_labels if x != -1]
          # test_accuracy_baseline_pos = [x for x in test_accuracy_baseline if x != -1]

          # mean_test_accuracy = sum(test_accuracy_labels_pos)/len(test_accuracy_labels)
          # mean_accuracy_baseline = sum(test_accuracy_baseline_pos)/len(test_accuracy_baseline)

          if test_accuracy > test_accuracy_baseline:
            print('saving checkpoint {}...'.format(checkpoint_num))
            voxnet.npz_saver.save(session, self.dataLoader.Output + '/c-{}.npz'.format(checkpoint_num))
            with open(self.dataLoader.Output + '/accuracies.txt', 'a') as f:
              f.write(' '.join(map(str, (checkpoint_num, training_accuracy, test_accuracy)))+'\n')
            with open(self.dataLoader.Output + '/accuracies_labels.txt', 'a') as f:
              f.write(str(checkpoint_num) + " ")
              for i in test_accuracy_labels:
                f.write(str(i) + " ")
              f.write('\n')
              print('checkpoint saved!')
            test_accuracy_baseline = test_accuracy

          checkpoint_num += 1

    return

  def get_keras_model(self):
    input = tf.keras.layers.Input(batch_shape = (None, self.dataLoader.XBins, self.dataLoader.YBins, self.dataLoader.ZBins, 1))
    conv_1 = tf.keras.layers.Conv3D(32, 5, 2, 'valid')(input)
    batch_1 = tf.keras.layers.BatchNormalization()(conv_1)
    max_1 = tf.keras.layers.LeakyReLU(alpha = 0.1)(batch_1)

    conv_2 = tf.keras.layers.Conv3D(32, 3, 1, 'valid')(max_1)
    batch_2 = tf.keras.layers.BatchNormalization()(conv_2)
    max_2 = tf.keras.layers.LeakyReLU(alpha = 0.1)(batch_2)

    max_pool_3d = tf.keras.layers.MaxPooling3D(pool_size = (2,2,2), strides = 2)(max_2)

    reshape = tf.keras.layers.Flatten()(max_pool_3d)

    dense_1 = tf.keras.layers.Dense(64)(reshape)
    batch_5 = tf.keras.layers.BatchNormalization()(dense_1)
    activation = tf.keras.layers.ReLU()(batch_5)

    drop = tf.keras.layers.Dropout(0.2)(activation)
    dense_2 = tf.keras.layers.Dense(64)(drop)

    print("      ... output layer ...")
    output = tf.keras.layers.Softmax()(dense_2)

    model = tf.keras.models.Model(inputs = input, outputs = output)
    model.compile(optimizer = 'adam', loss = 'categorical_crossentropy', metrics = ['accuracy'])
    self.dataLoader.keras_model = model

    # Session configuration
    print("      ... configuration ...")
    Config = tf.ConfigProto()
    Config.gpu_options.allow_growth = True

    # Create and initialize the session
    print("      ... session ...")
    Session = tf.Session(config=Config)
    Session.run(tf.global_variables_initializer())

    print("      ... listing uninitialized variables if there are any ...")
    print(tf.report_uninitialized_variables())

    print("      ... writer ...")
    writer = tf.summary.FileWriter(self.dataLoader.OutputDirectory, Session.graph)
    writer.close()

    # Add ops to save and restore all the variables.
    print("      ... saver ...")
    Saver = tf.train.Saver()

    K = tf.keras.backend
    K.set_session(Session)
    return model

  def trainKerasMethods(self):
    voxnet = self.dataLoader.get_keras_model()
    TimeConverting = 0.0
    TimeTraining = 0.0
    TimeTesting = 0.0

    Iteration = 0
    MaxIterations = 50000
    TimesNoImprovement = 0
    MaxTimesNoImprovement = 50
    while Iteration < MaxIterations:
      Iteration += 1
      print("\n\nStarting iteration {}".format(Iteration))

      # Step 1: Loop over all training batches
      for Batch in range(0, NTrainingBatches):

        # Step 1.1: Convert the data set into the input and output tensor
        TimerConverting = time.time()

        InputTensor = np.zeros(shape=(self.dataLoader.BatchSize, self.dataLoader.XBins, self.dataLoader.YBins, self.dataLoader.ZBins, 1))
        OutputTensor = np.zeros(shape=(self.dataLoader.BatchSize, self.dataLoader.OutputDataSpaceSize))

        # Loop over all training data sets and add them to the tensor
        for g in range(0, self.dataLoader.BatchSize):
          Event = TrainingDataSets[g + Batch*self.dataLoader.BatchSize]
          # Set the layer in which the event happened
          if Event.OriginPositionZ > self.dataLoader.ZMin and Event.OriginPositionZ < self.dataLoader.ZMax:
            LayerBin = int ((Event.OriginPositionZ - self.dataLoader.ZMin) / ((self.dataLoader.ZMax- self.dataLoader.ZMin)/ self.dataLoader.ZBins) )
            OutputTensor[g][LayerBin] = 1
          else:
            OutputTensor[g][self.dataLoader.OutputDataSpaceSize-1] = 1

          # Set all the hit locations and energies
          for h in range(0, len(Event.X)):
            XBin = int( (Event.X[h] - self.dataLoader.XMin) / ((self.dataLoader.XMax - self.dataLoader.XMin) / self.dataLoader.XBins) )
            YBin = int( (Event.Y[h] - self.dataLoader.YMin) / ((self.dataLoader.YMax - self.dataLoader.YMin) / self.dataLoader.YBins) )
            ZBin = int( (Event.Z[h] - self.dataLoader.ZMin) / ((self.dataLoader.ZMax - self.dataLoader.ZMin) / self.dataLoader.ZBins) )
            if XBin >= 0 and YBin >= 0 and ZBin >= 0 and XBin < self.dataLoader.XBins and YBin < self.dataLoader.YBins and ZBin < self.dataLoader.ZBins:
              InputTensor[g][XBin][YBin][ZBin][0] = Event.E[h]

        TimeConverting += time.time() - TimerConverting

        # Step 1.2: Perform the actual training
        TimerTraining = time.time()
        #print("\nStarting training for iteration {}, batch {}/{}".format(Iteration, Batch, NTrainingBatches))
        #_, Loss = Session.run([Trainer, LossFunction], feed_dict={X: InputTensor, Y: OutputTensor})
        History = model.fit(InputTensor, OutputTensor)
        Loss = History.history['loss'][-1]
        TimeTraining += time.time() - TimerTraining

        Result = model.predict(InputTensor)

        for e in range(0, self.dataLoader.BatchSize):
            # Fetch real and predicted layers for training data
            real, predicted, uniqueZ = getRealAndPredictedLayers(self.dataLoader.OutputDataSpaceSize, OutputTensor, Result, e, Event)
            TrainingRealLayer = np.append(TrainingRealLayer, real)
            TrainingPredictedLayer = np.append(TrainingPredictedLayer, predicted)
            TrainingUniqueZLayer = np.append(TrainingUniqueZLayer, uniqueZ)

        if Interrupted == True: break

      # End for all batches

      # Step 2: Check current performance
      TimerTesting = time.time()
      print("\nCurrent loss: {}".format(Loss))
      Improvement = CheckPerformance()

      if Improvement == True:
        TimesNoImprovement = 0

        Saver.save(Session, "{}/Model_{}.ckpt".format(OutputDirectory, Iteration))

        with open(OutputDirectory + '/Progress.txt', 'a') as f:
          f.write(' '.join(map(str, (CheckPointNum, Iteration, Loss)))+'\n')

        print("\nSaved new best model and performance!")
        CheckPointNum += 1
      else:
        TimesNoImprovement += 1

      TimeTesting += time.time() - TimerTesting

      # Exit strategy
      if TimesNoImprovement == MaxTimesNoImprovement:
        print("\nNo improvement for {} iterations. Quitting!".format(MaxTimesNoImprovement))
        break;

      # Take care of Ctrl-C
      if Interrupted == True: break

      print("\n\nTotal time converting per Iteration: {} sec".format(TimeConverting/Iteration))
      print("Total time training per Iteration:   {} sec".format(TimeTraining/Iteration))
      print("Total time testing per Iteration:    {} sec".format(TimeTesting/Iteration))
        

###################################################################################################


  def get_batch(self, batch_size, train):
    """
    Main test function

    Returns
    -------
    bool
      True is everything went well, False in case of an error

    """

    rn = random.randint
    bs = batch_size
    #xmin = -55
    #ymin = -55
    #zmin = 0
    #xmax = 55
    #ymax = 55
    #zmax = 48

    if train:
      EventHits = self.dataLoader.EventHitsTrain
      EventTypes = self.dataLoader.EventTypesTrain
    else:
      EventHits = self.dataLoader.EventHitsTest
      EventTypes = self.dataLoader.EventTypesTest

    voxs = np.zeros([bs, self.dataLoader.XBins, self.dataLoader.YBins, self.dataLoader.ZBins, 1], dtype=np.float32)
    one_hots = np.zeros([bs, self.dataLoader.MaxLabel], dtype=np.float32)
    #fill event hits
    for bi in range(bs):
      self.dataLoader.LastEventIndex += 1
      if self.dataLoader.LastEventIndex == len(EventHits):
        self.dataLoader.LastEventIndex = 0
      while len(self.dataLoader.EventHitsTrain[self.dataLoader.LastEventIndex]) == 0:
        self.dataLoader.LastEventIndex += 1
        if self.dataLoader.LastEventIndex == len(EventHits):
          self.dataLoader.LastEventIndex = 0
      for i in EventHits[self.dataLoader.LastEventIndex]:
          xbin = (int) (((i[0] - self.dataLoader.XMin) / (self.dataLoader.XMax - self.dataLoader.XMin)) * self.dataLoader.XBins)
          ybin = (int) (((i[1] - self.dataLoader.YMin) / (self.dataLoader.YMax - self.dataLoader.YMin)) * self.dataLoader.YBins)
          zbin = (int) (((i[2] - self.dataLoader.ZMin) / (self.dataLoader.ZMax - self.dataLoader.ZMin)) * self.dataLoader.ZBins)
          #print(bi, xbin, ybin, zbin)
          voxs[bi, xbin, ybin, zbin] += i[3]
      #fills event types
      one_hots[bi][EventTypes[self.dataLoader.LastEventIndex]] = 1
      
    return voxs, one_hots


###################################################################################################
def getRealAndPredictedLayers(OutputDataSpaceSize, OutputTensor, Result, e, Event):
    real = 0
    predicted = 0
    unique = Event.unique
    for l in range(0, OutputDataSpaceSize):
        if OutputTensor[e][l] > 0.5:
            real = l
        if Result[e][l] > 0.5:
            predicted = l
    return real, predicted, unique

def CheckPerformance():
  global BestPercentageGood

  Improvement = False

  TotalEvents = 0
  BadEvents = 0

  # Step run all the testing batches, and detrmine the percentage of correct identifications
  # Step 1: Loop over all Testing batches
  for Batch in range(0, NTestingBatches):

    # Step 1.1: Convert the data set into the input and output tensor
    InputTensor = np.zeros(shape=(self.dataLoader.BatchSize, self.dataLoader.XBins, self.dataLoader.YBins, self.dataLoader.ZBins, 1))
    OutputTensor = np.zeros(shape=(self.dataLoader.BatchSize, self.dataLoader.OutputDataSpaceSize))


    # Loop over all testing  data sets and add them to the tensor
    for e in range(0, BatchSize):
      Event = TestingDataSets[e + Batch*BatchSize]
      # Set the layer in which the event happened
      if Event.OriginPositionZ > self.dataLoader.ZMin and Event.OriginPositionZ < self.dataLoader.ZMax:
        LayerBin = int ((Event.OriginPositionZ - self.dataLoader.ZMin) / ((self.dataLoader.ZMax- self.dataLoader.ZMin)/ self.dataLoader.ZBins) )
        #print("layer bin: {} {}".format(Event.OriginPositionZ, LayerBin))
        OutputTensor[e][LayerBin] = 1
      else:
        OutputTensor[e][self.dataLoader.OutputDataSpaceSize-1] = 1

      # Set all the hit locations and energies
      SomethingAdded = False
      for h in range(0, len(Event.X)):
        XBin = int( (Event.X[h] - self.dataLoader.XMin) / ((self.dataLoader.XMax - self.dataLoader.XMin) / self.dataLoader.XBins) )
        YBin = int( (Event.Y[h] - self.dataLoader.YMin) / ((self.dataLoader.YMax - self.dataLoader.YMin) / self.dataLoader.YBins) )
        ZBin = int( (Event.Z[h] - self.dataLoader.ZMin) / ((self.dataLoader.ZMax - self.dataLoader.ZMin) / self.dataLoader.ZBins) )
        #print("hit z bin: {} {}".format(Event.Z[h], ZBin))
        if XBin >= 0 and YBin >= 0 and ZBin >= 0 and XBin < self.dataLoader.XBins and YBin < self.dataLoader.YBins and ZBin < self.dataLoader.ZBins:
          InputTensor[e][XBin][YBin][ZBin][0] = Event.E[h]
          SomethingAdded = True

      if SomethingAdded == False:
        print("Nothing added for event {}".format(Event.ID))
        Event.print()


    # Step 2: Run it
    # Result = Session.run(Output, feed_dict={X: InputTensor})
    Result = model.predict(InputTensor)

    #print(Result[e])
    #print(OutputTensor[e])

    for e in range(0, BatchSize):
      TotalEvents += 1
      IsBad = False
      LargestValueBin = 0
      LargestValue = OutputTensor[e][0]
      for c in range(1, self.dataLoader.OutputDataSpaceSize) :
        if Result[e][c] > LargestValue:
          LargestValue = Result[e][c]
          LargestValueBin = c

      if OutputTensor[e][LargestValueBin] < 0.99:
        BadEvents += 1
        IsBad = True

        #if math.fabs(Result[e][c] - OutputTensor[e][c]) > 0.1:
        #  BadEvents += 1
        #  IsBad = True
        #  break

      # Fetch real and predicted layers for testing data
      real, predicted = getRealAndPredictedLayers(self.dataLoader.OutputDataSpaceSize, OutputTensor, Result, e)
      global TestingRealLayer
      global TestingPredictedLayer
      TestingRealLayer = np.append(TestingRealLayer, real)
      TestingPredictedLayer = np.append(TestingPredictedLayer, predicted)

      # Some debugging
      if Batch == 0 and e < 500:
        EventID = e + Batch*BatchSize + NTrainingBatches*BatchSize
        print("Event {}:".format(EventID))
        if IsBad == True:
          print("BAD")
        else:
          print("GOOD")
        DataSets[EventID].print()

        print("Results layer: {}".format(LargestValueBin))
        for l in range(0, self.dataLoader.OutputDataSpaceSize):
          if OutputTensor[e][l] > 0.5:
            print("Real layer: {}".format(l))
          #print(OutputTensor[e])
          #print(Result[e])

  PercentageGood = 100.0 * float(TotalEvents-BadEvents) / TotalEvents

  if PercentageGood > BestPercentageGood:
    BestPercentageGood = PercentageGood
    Improvement = True

  print("Percentage of good events: {:-6.2f}% (best so far: {:-6.2f}%)".format(PercentageGood, BestPercentageGood))

  return Improvement

# END
###################################################################################################
