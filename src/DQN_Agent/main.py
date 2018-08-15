import sys
sys.dont_write_bytecode = True

import sys
import agent
import environment as env
import tensorflow as tf
import hyperparameters.setups as setups

game = 'CarRacing'

fixed_1track_seed = [108]
fixed_3track_seed = [104, 106, 108]

# One curve
# training_environment = env.env_dict[game](type='OneCurve', detect_edges=True)

# Two curve
# training_environment = env.env_dict[game](type='ShortTrack')

# Fixed full track
detect_edges = True
detect_grass = True
training_environment = env.env_dict[game](seed=fixed_1track_seed, detect_edges=detect_edges, detect_grass=detect_grass)

testing_environment = env.env_dict[game](test=True, detect_edges=detect_edges, detect_grass=detect_grass)
control = agent.DQN_Agent(training_environment=training_environment, testing_environment=testing_environment, model_name=sys.argv[1], **setups.setup_dict[game]['general'])
# control.load("path/to/checkpoint/file")
control.set_training_parameters(**setups.setup_dict[game]['training'])
control.train()
