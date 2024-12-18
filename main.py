'''
TODO:
1. Making the code run properly(debuging the FAISS code??)
2. Figuring out how to handle the inconsistency between training data and prediction results.
3. Trying more advanced structure.
'''

import pathlib
import time
from typing import Literal

import dspy
from colorama import init
from dspy.evaluate import Evaluate
from dspy.teleprompt import BootstrapFewShot
from sklearn.model_selection import train_test_split

from src.agents import Agent
from src.dataloader import DataManager
from src.evaluation import EvaluationManager
from src.predict_model import ExchangeOfThought
from src.util import LanguageModel, PrefixedChatAdapter
from src.util import Persona

# Initialize colorama
init(autoreset=True)

# CONSTANTS
DEBUG: bool = True
SEED: int = 42
API: Literal['lambda', 'openai'] = 'lambda'
MAX_TOKEN: int = 100

lm_wrapper = LanguageModel(max_tokens=MAX_TOKEN, service=API)
custom_adapter = PrefixedChatAdapter()
dspy.configure(lm=lm_wrapper.lm, adapter=custom_adapter)

# TODO: check if /models exists and if not create
pathlib.Path("models").mkdir(parents=True, exist_ok=True)
pathlib.Path("data").mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    # Load training and test sets
    start = time.time()
    examples = DataManager.get_examples(pathlib.Path("data"), debug=DEBUG)

    # Split in 80% validation as this is what is suggested here https://dspy.ai/learn/optimization/overview/
    train_data, val_data = train_test_split(examples, test_size=0.8, random_state=SEED)

    # Set up Agents

    # agent_a = Agent(name="Agent A" )#, persona_promt=Persona.AGENT_A_new)
    # agent_b = Agent(name="Agent B" )#, persona_promt=Persona.AGENT_B_new)
    # agent_c = Agent(name="Agent C" )#, persona_promt=Persona.AGENT_C_new)

    agent_a = Agent(name="Agent A" , persona_promt=Persona.AGENT_A_new)
    agent_b = Agent(name="Agent B" , persona_promt=Persona.AGENT_B_new)
    agent_c = Agent(name="Agent C" , persona_promt=Persona.AGENT_C_new)

    predict = ExchangeOfThought(
        agent_a, agent_b, agent_c, rounds=1, mode="Report")
    # predict = Agent(name="Single Agent" )
    evaluation_metric = EvaluationManager().metric_vector_search

    # compile
    #teleprompter = BootstrapFewShot(metric=evaluation_metric, max_labeled_demos=3)
    teleprompter = dspy.MIPROv2(metric=evaluation_metric, auto='medium', num_threads=6)
    compiled_predictor = teleprompter.compile(predict, trainset=train_data, requires_permission_to_run=False)
    #compiled_predictor = teleprompter.compile(predict, trainset=train_data)
    compiled_predictor.save("models" / pathlib.Path('compiled_model.dspy'))

    # evaluate
    evaluate_program = Evaluate(devset=val_data, metric=evaluation_metric,
                                num_threads=24, display_progress=True, display_table=10)

    eval_result = evaluate_program(predict)
    end = time.time()
    usage = lm_wrapper.get_usage()
    print(eval_result)
    print(f"Usage cost (in cents) about {usage[2]}, Input Tokens: {usage[0]}, Output Tokens {usage[1]}" )
    print("Time taken (in seconds)", end - start)

    # evaluate again
    # eval_compiled = evaluate_program(compiled_predictor)
    # compiled_predictor.save('./compiled_model.pkl')
    # print(eval_compiled)
