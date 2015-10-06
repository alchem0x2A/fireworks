from __future__ import division
from collections import defaultdict
from pymongo import DESCENDING
from tabulate import tabulate
from fireworks import LaunchPad

__author__ = 'Anubhav Jain <ajain@lbl.gov>'

def flatten_to_keys(curr_doc, curr_recurs=1, max_recurs=2):

    """
    Converts a dictionary into a list of keys, with string values "key1.key2:val"

    :param curr_doc:
    :param curr_recurs:
    :param max_recurs:
    :return: [<str>]
    """
    if isinstance(curr_doc, dict):
        if curr_recurs > max_recurs:
            return [":<TRUNCATED_OBJECT>"]
        my_list = []
        for k in curr_doc:
            for val in flatten_to_keys(curr_doc[k], curr_recurs+1, max_recurs):
                dot_char = '' if curr_recurs==1 else '.'
                my_list.append(dot_char+k+val)

        return my_list

    elif isinstance(curr_doc, list) or isinstance(curr_doc, tuple):
        my_list = []
        for k in curr_doc:
            if isinstance(k, dict) or isinstance(k, list) or isinstance(k, tuple):
                return [":<TRUNCATED_OBJECT>"]
            my_list.append(":"+str(k))
        return my_list

        return [flatten_to_keys(k, curr_recurs+1, max_recurs) for k in curr_doc]

    return [":"+str(curr_doc)]

def collect_stats(list_keys, filter_truncated=True):
    """
    Turns a list of keys (from flatten_to_keys) into a dict of <str>:count, i.e. counts the number of times each key appears
    :param list_keys:
    :param filter_truncated:
    :return:
    """
    d = defaultdict(int)
    for x in list_keys:
        if not filter_truncated or '<TRUNCATED_OBJECT>' not in x:
            d[x] += 1

    return d

def compare_stats(statsdict1, numsamples1, statsdict2, numsamples2, threshold=5):
    diff_dict = defaultdict(float)

    all_keys = statsdict1.keys()
    all_keys.extend(statsdict2.keys())
    all_keys = set(all_keys)
    for k in all_keys:
        if k in statsdict1:
            diff_dict[k] += (statsdict1[k]/numsamples1) * 100

        if k in statsdict2:
            diff_dict[k] -= (statsdict2[k]/numsamples2) * 100

        if abs(diff_dict[k]) < threshold:
            del(diff_dict[k])

    return diff_dict


class Introspector():
    def __init__(self, lpad):
            """
            :param lpad: (LaunchPad)
            """
            self.db = lpad.db

    def introspect_fizzled(self, coll="fws", rsort=True, threshold=10, limit=100):

        # initialize collection
        if coll.lower() in ["fws", "fireworks"]:
            coll = "fireworks"
            state_key = "spec"

        elif coll.lower() in ["tasks"]:
            coll = "fireworks"
            state_key = "spec._tasks"

        elif coll.lower() in ["wflows", "workflows"]:
            coll = "workflows"
            state_key = "metadata"
        else:
            raise ValueError("Unrecognized collection!")

        if rsort:
            sort_key=[("updated_on", DESCENDING)]
        else:
            sort_key=None

        # get stats on fizzled docs
        fizzled_keys = []
        nsamples_fizzled = 0

        for doc in self.db[coll].find({"state": "FIZZLED"}, {state_key: 1}, sort=sort_key).limit(limit):
            nsamples_fizzled += 1
            if state_key == "spec._tasks":
                for t in doc['spec']['_tasks']:
                    fizzled_keys.append('_fw_name:{}'.format(t['_fw_name']))
            else:
                fizzled_keys.extend(flatten_to_keys(doc[state_key]))

        fizzled_d = collect_stats(fizzled_keys)

        # get stats on completed docs
        completed_keys = []
        nsamples_completed = 0

        for doc in self.db[coll].find({"state": "COMPLETED"}, {state_key: 1}, sort=sort_key).limit(limit):
            nsamples_completed += 1
            if state_key == "spec._tasks":
                for t in doc['spec']['_tasks']:
                    completed_keys.append('_fw_name:{}'.format(t['_fw_name']))
            else:
                completed_keys.extend(flatten_to_keys(doc[state_key]))

        completed_d = collect_stats(completed_keys)

        diff_d = compare_stats(completed_d, nsamples_completed, fizzled_d, nsamples_fizzled, threshold=threshold)

        table = []
        for w in sorted(diff_d, key=diff_d.get, reverse=True):
            table.append([w.split(":")[0], w.split(":")[1], completed_d.get(w, 0), fizzled_d.get(w, 0), diff_d[w]])

        return table

    def print_report(self, table, coll=None):

        if coll:
            if coll.lower() in ["fws", "fireworks"]:
                coll = "fireworks.spec"
            elif coll.lower() in ["tasks"]:
                coll = "fireworks.spec._tasks"
            elif coll.lower() in ["wflows", "workflows"]:
                coll = "workflows.metadata"

            coll = "Introspection report for {}".format(coll)
            print('=' * len(coll))
            print(coll)
            print('=' * len(coll))

        print(tabulate(table, headers=['key', 'value', '#C', '#F', '%C - %F']))

