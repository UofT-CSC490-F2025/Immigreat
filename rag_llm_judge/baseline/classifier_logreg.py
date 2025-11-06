# classifier_logreg.py
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


def load_data(path):
    texts, labels, originals = [], [], []
    for line in open(path):
        ex = json.loads(line)
        combined = f"{ex['question']} {ex['answer']}"
        texts.append(combined)
        labels.append(ex['label'])
        originals.append(ex)
    return texts, labels, originals


def run_logreg(train_file, test_file, output_file):
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Load and embed training data
    X_train_texts, y_train, _ = load_data(train_file)
    X_train = model.encode(X_train_texts)

    # Train logistic regression
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train, y_train)

    # Evaluate on test data
    X_test_texts, y_test, test_examples = load_data(test_file)
    X_test = model.encode(X_test_texts)
    preds = clf.predict(X_test)

    print("\nLogistic Regression Evaluation:")
    print(classification_report(y_test, preds))

    # Write predictions to file
    with open(output_file, 'w') as f_out:
        for ex, pred in zip(test_examples, preds):
            ex['logreg_prediction'] = int(pred)
            f_out.write(json.dumps(ex) + "\n")
