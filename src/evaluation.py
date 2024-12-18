import pathlib

import dspy
import numpy as np

from src.agents import SummeryAgent
from src.dataloader import DataManager
from src.db import MisconceptionDB
from src.util import LanguageModel
from typing import Literal
import os

class SimpleScorerAgentSignature(dspy.Signature):
    """Predict the similarity score between the groundtruth and prediction. Focus on how similar the content is only. Give a high score if the content is the same. Give a low score if the content is different. Provide a score between 0 and 1.
    """
    groundtruth: str = dspy.InputField()
    prediction: str = dspy.InputField()
    score = dspy.OutputField()

# Evaluating the answer
class EvaluationManager:
    def __init__(self):
        self.misconception_db = MisconceptionDB("data" / pathlib.Path("misconception_mapping.csv"))
        self.misconceptions_df = DataManager.get_misconceptions("data" / pathlib.Path("misconception_mapping.csv"))
        self.summery_agent = SummeryAgent(name='Summery Agent')

    @staticmethod
    def metric(gold, pred, trace=None):
        # Ensure prediction_score is a float
        try:
            print(f"pred: {pred}")
            prediction = dspy.ChainOfThought(SimpleScorerAgentSignature)(groundtruth=gold.MisconceptionText,
                                                                         prediction=pred)
            score = float(prediction.score.strip())
        except:
            score = 0.01
        return max(0.0, min(1.0, score))

    #def metric(gold, pred, trace=None):
    # db.vector_search(pred, k=1) --> List [Tuple[int class_id, float distance]]
    # sort by distance, lowestance first
    # MAP_25 gold_class_id and np.array[25 prediction class_id] -- score: float
    # MAP_25(List [Tuple[int class_id, float distance]], gold) --> gold.class_id


    # def l2_distance(self, gold, pred, trace=None):
    #     return evaluate_answers(gold, pred, trace)

    # This function is probably not working anymore because it's
    def evaluate_answers(self, gold, pred, trace=None):

        try:
            gold_answer_id = gold.answer
            mis_out = self.summery_agent(pred.question, pred.answer)
            print(f"mis_out: {mis_out}")

            final_index = []
            for mis in [mis_out.misconceptionA, mis_out.misconceptionB, mis_out.misconceptionC, mis_out.misconceptionD]:
                final_index.append(self.misconception_db.hybrid_search(mis)[
                                   0].misconception_id)

            for i, mis in enumerate(final_index):
                if mis == gold_answer_id[i]:
                    return True
            return False

        except:
            return False
    
    def map_at_25(self, misconception: str, ground_truth: int):
        """
        misconception: str - the misconception text returned by th EoT model
        ground_truth: int - the ground truth misconception id

        returns: float - the MAP@25 score
        """
        searched_misconceptions = self.misconception_db.hybrid_search(misconception, top_k=25, pre_filter_k=50)
        misconception_ids = [misconception.misconception_id for misconception in searched_misconceptions]
        cutoff = min(len(misconception_ids), 25)
        for k, pred_id in enumerate(misconception_ids[:cutoff]):
            if int(pred_id)==ground_truth:
                return 1.0/(k+1) #we only consider one unique label as relavent for each observation
        return 0.0

    # implements the MAP@25 evaluation metric
    # layout prediction array: is a 2D Array with shape (n, 25) where n is the number of questions in the dataset
    # layout prediction array: is a 1D Array with shape (n) where n is the number of questions in the dataset
    @staticmethod
    def calculate_map_at_25(predictions: np.array, ground_truth: np.array) -> float:
        if predictions.shape[0] != ground_truth.shape[0]:
            raise IndexError("The num_sample of predictions doesn't match the num_sample of groundtruths")
        U = ground_truth.shape[0]
        cutoff = min(predictions.shape[1], 25)
        total_ap = []
        for u in range(U):
            ap = 0.0
            true_label = ground_truth[u]
            prediction = predictions[u]
            for k in range(cutoff):
                predicted_label = prediction[k]
                if predicted_label==true_label:
                    ap = 1.0/(k+1) #we only consider one unique label as relavent for each observation
                    break
            total_ap.append(ap)
        return np.mean(total_ap) if total_ap else 0.0

    def metric_vector_search(self, gold: dspy.Example, pred: str, trace=None) -> float:
        """
        Calculates the MAP@25 score for a single prediction using vector search.

        Args:
            gold (dspy.Example): The gold example containing the ground truth misconception ID.
            pred (str): The predicted misconception text.
            trace: Optional trace information (not used).

        Returns:
            float: The MAP@25 score for the prediction.
        """
        if pred == "Failed to generate misconception explanation.":
            return 0.0
        # Extract the ground truth misconception ID from the gold example
        ground_truth_id = gold.MisconceptionId  # Assuming gold.answer holds the MisconceptionId

        # Perform vector search to retrieve top 25 similar misconceptions
        search_results = self.misconception_db.vector_search(pred, k=25)

        # Map the search result indices to MisconceptionIds
        predicted_class_ids = [
            self.misconception_db.df.iloc[idx]['MisconceptionId'] for idx, _ in search_results
        ]

        # Prepare numpy arrays for calculate_map_at_25
        predictions = np.array([predicted_class_ids])
        ground_truth = np.array([ground_truth_id])

        # Calculate MAP@25 using the existing method
        map25_score = self.calculate_map_at_25(predictions, ground_truth)

        return map25_score

if __name__ == "__main__":
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    
    llm = dspy.LM('openai/gpt-4o-mini', max_tokens=130, api_key=OPENAI_API_KEY)
    dspy.configure(lm=llm)
    evaluation_manager = EvaluationManager()
    print(evaluation_manager.misconception_db.hybrid_search("doesn't know triangle's shape", top_k=5, pre_filter_k=5))
    print(evaluation_manager.map_at_25("doesn't know triangle's shape", 1279))