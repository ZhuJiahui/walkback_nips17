'''
'''

import argparse
import numpy as np
import os
#import warnings

import mimir


import theano
import theano.tensor as T
#from theano.tensor.shared_randomstreams import RandomStreams

from collections import OrderedDict
#from blocks.algorithms import (RMSProp, GradientDescent, CompositeRule, RemoveNotFinite)
#from blocks.extensions import FinishAfter, Timing, Printing
#from blocks.extensions.monitoring import (DataStreamMonitoring, TrainingDataMonitoring)
#from blocks.extensions.saveload import Checkpoint
#from blocks.extensions.training import SharedVariableModifier
#from blocks.filter import VariableFilter
#from blocks.graph import ComputationGraph, apply_dropout
#from blocks.main_loop import MainLoop
#import blocks.model
#from blocks.roles import INPUT#, PARAMETER

from fuel.streams import DataStream
from fuel.schemes import ShuffledScheme, SequentialScheme
#from fuel.transformers import Flatten#, ScaleAndShift
from fuel.datasets.toy import Spiral
import optimizers
#import extensions
#import model
from util import  unzip, norm_weight, _p, itemlist,  load_params, create_log_dir,  save_params  #ortho_weight
#import ipdb
#from viz import plot_images
import sys

def plot_images(X, fname):
    np.savez(fname + '.npz', X=X)
import itertools
import numpy
from datasets import GaussianMixture


MEANS = [numpy.array([i, j]) for i, j in itertools.product(range(-1, 2, 1),
                                                           range(-1, 2, 1))]
VARIANCES = [0.05 ** 2 * numpy.eye(len(mean)) for mean in MEANS]
PRIORS = None

from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams
rng = RandomStreams(12345)
from viz import plot_2D, plot_grad
sys.setrecursionlimit(10000000)
import ipdb
#import lasagne

class ConsiderConstant(theano.compile.ViewOp):
    def grad(self, args, g_outs):
        return [T.zeros_like(g_out) for g_out in g_outs]

consider_constant = ConsiderConstant()
#register_canonicalize(theano.gof.OpRemove(consider_constant), name='remove_consider_constant')
INPUT_SIZE = 2
use_conv = False

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch_size', default=500, type=int,
                        help='Batch size')
    parser.add_argument('--lr', default=0.0001, type=float,
                        help='Initial learning rate. ' + \
                        'Will be decayed until it\'s 1e-5.')
    parser.add_argument('--resume_file', default=None, type=str,
                        help='Name of saved model to continue training')
    parser.add_argument('--suffix', default='', type=str,
                        help='Optional descriptive suffix for model')
    parser.add_argument('--output-dir', type=str, default='./',
                        help='Output directory to store trained models')
    parser.add_argument('--ext-every-n', type=int, default=25,
                        help='Evaluate training extensions every N epochs')
    parser.add_argument('--model-args', type=str, default='',
                        help='Dictionary string to be eval()d containing model arguments.')
    parser.add_argument('--dropout_rate', type=float, default=0.,
                        help='Rate to use for dropout during training+testing.')
    parser.add_argument('--dataset', type=str, default='CIFAR10',
                        help='Name of dataset to use.')
    parser.add_argument('--plot_before_training', type=bool, default=False,
                        help='Save diagnostic plots at epoch 0, before any training.')
    parser.add_argument('--num_steps', type=int, default=2,
                        help='Number of transition steps.')
    parser.add_argument('--temperature', type=float, default=1.0,
                        help='Standard deviation of the diffusion process.')
    parser.add_argument('--alpha', type=float, default=0.5,
                        help='alpha factor')
    parser.add_argument('--dims', default=[4096], type=int,
                        nargs='+')
    parser.add_argument('--noise_prob', default=0.1, type=float,
                        help='probability for bernouli distribution of adding noise of 1 to each input')
    parser.add_argument('--avg', default=0, type=float)
    parser.add_argument('--std', default=1., type=float)
    parser.add_argument('--noise', default='gaussian', choices=['gaussian', 'binomial'])
    parser.add_argument('--reload_', type=bool, default = False,
                        help='Reloading the parameters')
    parser.add_argument('--saveto_filename', type = str, default = None,
                        help='directory where parameters are stored')
    parser.add_argument('--extra_steps', type = int, default = 0,
                        help='Number of extra steps to sample at temperature 1')
    parser.add_argument('--meta_steps', type = int, default = 1,
                        help='Number of extra steps to sample at temperature 1')
    parser.add_argument('--optimizer', type = str, default = 'sgd',
                        help='optimizer we are going to use!!')
    parser.add_argument('--temperature_factor', type = float, default = 2.0,
                        help='How much temperature must be scaled')
    parser.add_argument('--sigma', type = float, default = 0.01,
                        help='Initial variance added at first step!')

    args = parser.parse_args()

    model_args = eval('dict(' + args.model_args + ')')
    print model_args


    if not os.path.exists(args.output_dir):
        raise IOError("Output directory '%s' does not exist. "%args.output_dir)
    return args, model_args


def param_init_fflayer(options, params, prefix='ff',
                       nin=None, nout=None, ortho=True, flag=False):

    if nin is None:
        nin = options['dim_proj']
    if nout is None:
        nout = options['dim_proj']
    params[_p(prefix, 'W')] = norm_weight(nin, nout, scale=0.01, ortho=ortho)
    flag = False
    if flag:
        #params[_p(prefix, 'b')] = np.full(nout,-1).astype('float32')
        import gzip
        import pickle
        with gzip.open('mnist.pkl.gz', 'rb') as f:
            train_set, _ , _ = pickle.load(f)
            train_x, train_y = train_set
            marginals = np.clip(train_x.mean(axis=0), 1e-7, 1- 1e-7)
            initial_baises = np.log(marginals/(1-marginals))
            params[_p(prefix, 'b')] = initial_baises.astype('float32')

    else:
        params[_p(prefix, 'b')] = np.zeros((nout,)).astype('float32')

    return params

from fuel.datasets import IndexableDataset
from fuel import config
class Circle(IndexableDataset):
     def __init__(self, num_examples=1000, classes=1, cycles=1., noise=0.0, **kwargs):
         seed = kwargs.pop('seed', config.default_seed)
         rng = np.random.RandomState(seed)
         # Create dataset
         pos = rng.uniform(size=num_examples, low=0, high=cycles)
         label = rng.randint(size=num_examples, low=0, high=classes)
         radius = 1 #(2 * pos + 1) / 3.
         phase_offset = label * (2*np.pi) / classes

         features = np.zeros(shape=(num_examples, 2), dtype='float32')

         features[:, 0] = radius * np.sin(2*np.pi*pos + phase_offset)
         features[:, 1] = radius * np.cos(2*np.pi*pos + phase_offset)
         features += noise * rng.normal(size=(num_examples, 2))

         data = OrderedDict([
             ('features', features),
             ('position', pos),
             ('label', label),
         ])

         super(Circle, self).__init__(data, **kwargs)

def init_tparams(params):
    tparams = OrderedDict()
    for kk, pp in params.iteritems():
        tparams[kk] = theano.shared(params[kk], name=kk)
        print kk
    return tparams


layers = {'ff': ('param_init_fflayer', 'fflayer')}

def get_layer(name):
        fns = layers[name]
        return (eval(fns[0]), eval(fns[1]))


def fflayer(tparams, state_below, options, prefix='rconv',
            activ='lambda x: tensor.tanh(x)', **kwargs):
    return T.dot(state_below, tparams[_p(prefix, 'W')]) + tparams[_p(prefix, 'b')]



def init_params(options):

    params = OrderedDict()

    if not use_conv:

        params = get_layer('ff')[0](options, params, prefix='layer_1',
                                nin=INPUT_SIZE, nout=args.dims[0],
                                ortho=False)

        params = get_layer('ff')[0](options, params, prefix='layer_2',
                                nin=args.dims[0], nout=args.dims[0],
                                ortho=False)
        #TODO: Ideally, only in the output layer, flag=True should be set.
        if len(args.dims) == 1:
            params = get_layer('ff')[0](options, params, prefix='mu_0',
                                nin=args.dims[0], nout=INPUT_SIZE,
                                ortho=False, flag=True)
            if args.noise == 'gaussian':
                params = get_layer('ff')[0](options, params, prefix='sigma_0',
                                        nin=args.dims[0], nout=INPUT_SIZE,
                                        ortho=False)


        for i in range(len(args.dims)-1):
                params = get_layer('ff')[0](options, params, prefix ='mu_'+str(i),
                                    nin=args.dims[i], nout=args.dims[i+1],
                                    ortho=False)
                if args.noise == 'gaussian':
                    params = get_layer('ff')[0](options, params, prefix='sigma_'+str(i),
                                    nin=args.dims[i], nout=args.dims[i+1],
                                    ortho=False, flag=True )


        if len(args.dims) > 1:
            params = get_layer('ff')[0](options, params, prefix='mu_'+str(i+1),
                                    nin=args.dims[i+1], nout=INPUT_SIZE,
                                    ortho=False, flag=True)

            if args.noise == 'gaussian':
                params = get_layer('ff')[0](options, params, prefix='sigma_'+str(i+1),
                                    nin=args.dims[i+1], nout=INPUT_SIZE,
                                    ortho=False)
    return params

# P(next s | previous s) as a gaussian with mean = (1-alpha)*previous_s + alpha * F(previous_s) + sigma(previous_s)*Gaussian_noise(0,1)
# where we learn the functions F and sigma (e.g. as MLPs), with sigma>0 by construction.

def join(a, b=None):
    if b==None:
        return a
    else:
        return T.concatenate([a,b],axis=1)

def ln(inp):
    return (inp - T.mean(inp,axis=1,keepdims=True)) / (0.001 + T.std(inp,axis=1,keepdims=True))

#from lasagne.layers import batch_norm
#from lib.ops import batchnorm
def transition_operator(tparams, options, x, temperature):
     h1 = T.nnet.relu(fflayer(tparams, x, options,prefix='layer_1'), alpha = 0.02)
     h2 = T.nnet.relu(fflayer(tparams, h1, options,prefix='layer_2'), alpha = 0.02)
     h = h2

     for i in range(len(args.dims)):
         if i == 0:
             mu = fflayer(tparams, h, options, prefix='mu_0')
             if args.noise == 'gaussian':
                 sigma = fflayer(tparams, h, options, prefix='sigma_0')
         else:
             mu = fflayer(tparams, mu, options, prefix='mu_' + str(i))
             if args.noise == 'gaussian':
                 sigma = fflayer(tparams, sigma, options, prefix='sigma_' + str(i))

     if args.noise == 'gaussian':
         sigma = T.nnet.softplus(sigma)
         sigma = args.sigma * sigma * T.sqrt(temperature)
         epsilon = rng.normal(size=(args.batch_size, INPUT_SIZE), avg=args.avg, std=args.std, dtype=theano.config.floatX)
         x_hat = consider_constant((args.alpha)*x + (1-args.alpha) * (mu) +  T.sqrt(sigma) * epsilon)
         mean_ = ((args.alpha)*x + (1-args.alpha) * (mu))
         log_p_reverse = -0.5 * T.sum(1.0 * (T.log(2 * np.pi) + T.log(sigma) + (x - mean_) ** 2 / (sigma)),[1])
         return x_hat, log_p_reverse, sigma, mean_



def sample(tparams, options):
    #batch_size = 32
    x_data = T.matrix('x_sample', dtype='float32')
    temperature = T.scalar('temperature_sample', dtype='float32')
    x_tilde, _, sampled, sampled_activation  = transition_operator(tparams, options, x_data, temperature)
    f = theano.function([x_data, temperature], [x_tilde, sampled])
    return f

#from distributions import log_normal1
def compute_loss(x, options, tparams, start_temperature):
     temperature = start_temperature
     x_tilde, log_p_reverse, _, _ = transition_operator(tparams, options, x, temperature)

     states = [x_tilde]
     log_p_reverse_list = [log_p_reverse]
     print args.num_steps
     for _ in range(args.num_steps - 1):
         temperature *= args.temperature_factor
         x_tilde, log_p_reverse, _,_ = transition_operator(tparams, options, states[-1], temperature)
         states.append(x_tilde)
         log_p_reverse_list.append(log_p_reverse)
     #mean_ = x_tilde.mean(axis=0)
     #var_ = x_tilde.mean(axis=0)
     #log_loss = log_normal1(x_tilde, T.addbroadcast(mean_, 1), T.addbroadcast(var_, 1))
     #log_p_reverse_list.append(log_loss)
     loss = -T.mean(sum(log_p_reverse_list, 0.0))

     return loss

def one_step_diffusion(x, options, tparams, temperature):
    x_tilde, log_p_reverse, sampled, sampled_activation = transition_operator(tparams, options, x, temperature)

    forward_diffusion =  theano.function([x, temperature], [x_tilde, sampled, sampled_activation, sampled_activation])
    return forward_diffusion

def build_model(tparams, model_options):
    x = T.matrix('x', dtype='float32')
    start_temperature = T.scalar('start_temperature', dtype='float32')
    loss = compute_loss(x, model_options, tparams, start_temperature)
    return x, loss, start_temperature

def train(args,
          model_args):

    model_id = '/data/lisatmp3/anirudhg/spiral_walk_back/walkback_'
    model_dir = create_log_dir(args, model_id)
    model_id2 =  'logs/walkback_'
    model_dir2 = create_log_dir(args, model_id2)
    print model_dir
    print model_dir2 + '/' + 'log.jsonl.gz'
    logger = mimir.Logger(filename=model_dir2  + '/log.jsonl.gz', formatter=None)

    # TODO batches_per_epoch should not be hard coded
    lrate = args.lr
    import sys
    sys.setrecursionlimit(10000000)
    args, model_args = parse_args()

    #trng = RandomStreams(1234)

    if args.resume_file is not None:
        print "Resuming training from " + args.resume_file
        from blocks.scripts import continue_training
        continue_training(args.resume_file)

    ## load the training data
    if args.dataset == 'MNIST':
        print 'loading MNIST'
        from fuel.datasets import MNIST
        dataset_train = MNIST(['train'], sources=('features',))
        dataset_test = MNIST(['test'], sources=('features',))
        n_colors = 1
        spatial_width = 28

    elif args.dataset == 'CIFAR10':
        from fuel.datasets import CIFAR10
        dataset_train = CIFAR10(['train'], sources=('features',))
        dataset_test = CIFAR10(['test'], sources=('features',))
        n_colors = 3
        spatial_width = 32

    elif args.dataset == "lsun" or args.dataset == "lsunsmall":

        print "loading lsun class!"

        from load_lsun import load_lsun

        print "loading lsun data!"

        if args.dataset == "lsunsmall":
            dataset_train, dataset_test = load_lsun(args.batch_size, downsample=True)
            spatial_width=32
        else:
            dataset_train, dataset_test = load_lsun(args.batch_size, downsample=False)
            spatial_width=64

        n_colors = 3


    elif args.dataset == "celeba":

        print "loading celeba data"

        from fuel.datasets.celeba import CelebA

        dataset_train = CelebA(which_sets = ['train'], which_format="64", sources=('features',), load_in_memory=False)
        dataset_test = CelebA(which_sets = ['test'], which_format="64", sources=('features',), load_in_memory=False)

        spatial_width = 64
        n_colors = 3

        tr_scheme = SequentialScheme(examples=dataset_train.num_examples, batch_size=args.batch_size)
        ts_scheme = SequentialScheme(examples=dataset_test.num_examples, batch_size=args.batch_size)

        train_stream = DataStream.default_stream(dataset_train, iteration_scheme = tr_scheme)
        test_stream = DataStream.default_stream(dataset_test, iteration_scheme = ts_scheme)

        dataset_train = train_stream
        dataset_test = test_stream

        #epoch_it = train_stream.get_epoch_iterator()

    elif args.dataset == 'Spiral':
        print 'loading SPIRAL'
        train_set = Spiral(num_examples=20000, classes=1, cycles=1., noise=0.01,
                           sources=('features',))
        dataset_train = DataStream.default_stream(train_set,
                            iteration_scheme=ShuffledScheme(
                            train_set.num_examples, args.batch_size))
    elif args.dataset == 'Circle':
         print 'loading Circle'
         train_set = Circle(num_examples=20000, classes=1, cycles=1., noise=0.0,
                            sources=('features',))
         dataset_train = DataStream.default_stream(train_set,
                             iteration_scheme=ShuffledScheme(
                             train_set.num_examples, args.batch_size))
         iter_per_epoch = train_set.num_examples
    elif args.dataset == 'MOG':
        print 'loading GOM'
        dataset = GaussianMixture(num_examples=20000,
                              means=MEANS, variances=VARIANCES, priors=None,
                              rng=None, sources=('features', 'label'))
        dataset_train = DataStream.default_stream(dataset,
                             iteration_scheme=ShuffledScheme(
                             dataset.num_examples, args.batch_size))
        features, targets = dataset.indexables
        #ipdb.set_trace()


    else:
        raise ValueError("Unknown dataset %s."%args.dataset)

    model_options = locals().copy()

    train_stream = dataset_train


    shp = next(train_stream.get_epoch_iterator())[0].shape

    print "got epoch iterator"

    # make the training data 0 mean and variance 1
    # TODO compute mean and variance on full dataset, not minibatch
    Xbatch = next(train_stream.get_epoch_iterator())[0]
    scl = 1./np.sqrt(np.mean((Xbatch-np.mean(Xbatch))**2))
    shft = -np.mean(Xbatch*scl)
    # scale is applied before shift
    #train_stream = ScaleAndShift(train_stream, scl, shft)
    #test_stream = ScaleAndShift(test_stream, scl, shft)

    print 'Building model'
    params = init_params(model_options)
    if args.reload_:
        print "Trying to reload parameters"
        if os.path.exists(args.saveto_filename):
            print 'Reloading Parameters'
            print args.saveto_filename
            params = load_params(args.saveto_filename, params)
    tparams = init_tparams(params)
    print tparams
    x, cost, start_temperature = build_model(tparams, model_options)
    inps = [x, start_temperature]

    x_Data = T.matrix('x_Data', dtype='float32')
    temperature  = T.scalar('temperature', dtype='float32')
    forward_diffusion = one_step_diffusion(x_Data, model_options, tparams, temperature)

    #print 'Building f_cost...',
    #f_cost = theano.function(inps, cost)
    #print 'Done'
    print tparams
    grads = T.grad(cost, wrt=itemlist(tparams))

    #get_grads = theano.function(inps, grads)

    for j in range(0, len(grads)):
        grads[j] = T.switch(T.isnan(grads[j]), T.zeros_like(grads[j]), grads[j])


    # compile the optimizer, the actual computational graph is compiled here
    lr = T.scalar(name='lr')
    print 'Building optimizers...',
    optimizer = args.optimizer

    f_grad_shared, f_update = getattr(optimizers, optimizer)(lr, tparams, grads, inps, cost)
    print 'Done'

    print 'Buiding Sampler....'
    f_sample = sample(tparams, model_options)
    print 'Done'
    uidx = 0
    estop = False
    bad_counter = 0
    max_epochs = 4000
    batch_index = 0
    print  'Number of steps....', args.num_steps
    print 'Done'
    count_sample = 1
    batch_index = 0
    for eidx in xrange(max_epochs):
        if eidx%20==0:
            params = unzip(tparams)
            save_params(params, model_dir + '/' + 'params_' + str(eidx) + '.npz')
            if eidx == 30:
                ipdb.set_trace()
        n_samples = 0
        print 'Starting Next Epoch ', eidx

        for data in train_stream.get_epoch_iterator():
            batch_index += 1
            n_samples += len(data[0])
            uidx += 1
            if data[0] is None:
                print 'No data '
                uidx -= 1
                continue
            data_run = data[0]
            temperature_forward = args.temperature
            meta_cost = []
            for meta_step in range(0, args.meta_steps):
                meta_cost.append(f_grad_shared(data_run, temperature_forward))
                f_update(lrate)
                if args.meta_steps > 1:
                    data_run, sigma, _, _ = forward_diffusion(data_run, temperature_forward)
                    temperature_forward *= args.temperature_factor
            cost = sum(meta_cost) / len(meta_cost)
            if np.isnan(cost) or np.isinf(cost):
                print 'NaN detected'
                return 1.
            logger.log({'epoch': eidx,
                        'batch_index': batch_index,
                        'uidx': uidx,
                        'training_error': cost})
            empty = []
            spiral_x = [empty for i in range(args.num_steps)]
            spiral_corrupted = []
            spiral_sampled = []
            grad_forward = []
            grad_back = []
            x_data_time = []
            x_tilt_time = []
            if batch_index%8==0:
                count_sample += 1
                temperature = args.temperature * (args.temperature_factor ** (args.num_steps -1 ))
                temperature_forward = args.temperature
                for num_step in range(args.num_steps):
                    if num_step == 0:
                        x_data_time.append(data[0])
                        plot_images(data[0], model_dir + '/' + 'orig_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))
                        x_data, mu_data, _, _ = forward_diffusion(data[0], temperature_forward)

                        plot_images(x_data, model_dir + '/' + 'corrupted_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index) + '_time_step_' + str(num_step))
                        x_data_time.append(x_data)
                        temp_grad = np.concatenate((x_data_time[-2], x_data_time[-1]), axis=1)
                        grad_forward.append(temp_grad)

                        x_data = np.asarray(x_data).astype('float32').reshape(args.batch_size, INPUT_SIZE)
                        spiral_corrupted.append(x_data)
                        mu_data = np.asarray(mu_data).astype('float32').reshape(args.batch_size, INPUT_SIZE)
                        mu_data = mu_data.reshape(args.batch_size, 2)
                    else:
                        x_data_time.append(x_data)
                        x_data, mu_data, _, _ = forward_diffusion(x_data, temperature_forward)
                        plot_images(x_data, model_dir + '/' + 'corrupted_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index) + '_time_step_' + str(num_step))
                        x_data = np.asarray(x_data).astype('float32').reshape(args.batch_size, INPUT_SIZE)
                        spiral_corrupted.append(x_data)

                        mu_data = np.asarray(mu_data).astype('float32').reshape(args.batch_size, INPUT_SIZE)
                        mu_data = mu_data.reshape(args.batch_size, 2)
                        x_data_time.append(x_data)
                        temp_grad = np.concatenate((x_data_time[-2], x_data_time[-1]), axis=1)
                        grad_forward.append(temp_grad)
                    temperature_forward = temperature_forward * args.temperature_factor;

                mean_sampled = x_data.mean()
                var_sampled =  x_data.var()

                x_temp2 = data[0].reshape(args.batch_size, 2)
                plot_2D(spiral_corrupted, args.num_steps, model_dir + '/' + 'corrupted_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))
                plot_2D(x_temp2, 1, model_dir  + '/' + 'orig_' + 'epoch_' + str(count_sample) + '_batch_index_' +  str(batch_index))
                plot_grad(grad_forward, model_dir + '/' + 'grad_forward_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))
                for i in range(args.num_steps + args.extra_steps):
                    x_tilt_time.append(x_data)
                    x_data, sampled_mean  = f_sample(x_data, temperature)
                    plot_images(x_data, model_dir + '/' + 'sampled_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index) + '_time_step_' + str(i))
                    x_tilt_time.append(x_data)
                    temp_grad = np.concatenate((x_tilt_time[-2], x_tilt_time[-1]), axis=1)
                    grad_back.append(temp_grad)

                    ###print 'Recons, On step number, using temperature', i, temperature
                    x_data = np.asarray(x_data).astype('float32')
                    x_data = x_data.reshape(args.batch_size, INPUT_SIZE)
                    if temperature == args.temperature:
                        temperature = temperature
                    else:
                        temperature /= args.temperature_factor

                plot_grad(grad_back, model_dir + '/' + 'grad_back_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))
                plot_2D(x_tilt_time,args.num_steps, model_dir + '/' + 'sampled_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))

                s = np.random.normal(mean_sampled, var_sampled, [args.batch_size, 2])
                x_sampled = s


                temperature = args.temperature * (args.temperature_factor ** (args.num_steps -1 ))
                x_data = np.asarray(x_sampled).astype('float32')
                for i in range(args.num_steps + args.extra_steps):
                    x_data, sampled_mean = f_sample(x_data, temperature)
                    spiral_sampled.append(x_data)
                    x_data = np.asarray(x_data).astype('float32')
                    x_data = x_data.reshape(args.batch_size, INPUT_SIZE)
                    if temperature == args.temperature:
                        temperature = temperature
                    else:
                        temperature /= args.temperature_factor
                plot_2D(spiral_sampled, args.num_steps, model_dir + '/' + 'inference_' + 'epoch_' + str(count_sample) + '_batch_' +  str(batch_index))
    ipdb.set_trace()

if __name__ == '__main__':
    args, model_args = parse_args()
    train(args, model_args)
    pass
