import json
import os
import re
import requests
import sys
import warnings

from colorama import init, Fore, Back, Style
from datetime import date
from scipy.stats import kendalltau

PLAYER_ID_CACHE = dict()
POSITION_POINTS_DICT = dict()
ALL_POSITIONS_LIST = ["qb", "rb", "wr", "te", "def"]

def fxn():
    warnings.warn("runtime", RuntimeWarning)

def sortPlayers(d):
	return d[1]['pts_ppr'] if 'pts_ppr' in d[1] else d[1]['pts_std']

def fixJsonFile(initial_path="players.json"):
	if not os.path.exists(initial_path):
		with open(initial_path, "w+") as file:
			response = requests.get("https://api.sleeper.app/v1/players/nfl")
			file.write(response.text)

	with open(initial_path) as json_file:
		text = json_file.read()

		text = re.sub(r'(\w)\"\",', '\g<1>\",', text) # Remove double-quotes following heights
		text = re.sub(r': (\w+)}?,', ': \"\g<1>\",', text) # E.g. replace False with "False"
		text = re.sub(r'(\w+)\"(\w+)', "\g<1>'\g<2>", text)
		text = re.sub(r': \"(\w+)\" ', ": \"\g<1>' ", text)

		text = text.replace("\"None\"", "\"\"")
		text = text.replace(" None,", " \"\",")
		text = text.replace(" None}", " \"\"}")

		text = re.sub(r'(\"rotowire_id\": \"[0-9]*\")', "\g<1>}", text) # Add a matching } for each player.
		text = re.sub(r'(\", \"([0-9]+)\": {\"college)', "\"}, \"\g<1>\": {\"college)}", text)

		text = text.replace(", \"\",", ", ")
		text = text.replace("{\"college)}\": ", "")
		text = text.replace("}}}", "}}")

		with open("players_fixed.json", "w+") as new_file:
			new_file.write(text)

def average(l):
	return sum(l) / len(l)

def getPositionResults(position, week, stats=None, top_n_to_print=0):
	global PLAYER_ID_CACHE, POSITION_POINTS_DICT

	if week < 0 or week > 17: return None

	with open("players_fixed.json") as json_file:
		players_dict = json.load(json_file)

	if not stats:
		response = requests.get("https://api.sleeper.app/v1/stats/nfl/regular/2019/{}".format(week))
		stats = response.json()

	stats_list = list()
	position = position.lower()

	if week not in POSITION_POINTS_DICT: POSITION_POINTS_DICT[week] = dict()
	if position.upper() not in POSITION_POINTS_DICT[week]: POSITION_POINTS_DICT[week][position.upper()] = list()

	for player_id in stats:

		if player_id not in players_dict: continue

		if 'full_name' in players_dict[player_id]:
			players_dict[player_id]['full_name'] = normalizePlayerName(players_dict[player_id]['full_name'])
			if players_dict[player_id]['full_name'] not in PLAYER_ID_CACHE:
				PLAYER_ID_CACHE[players_dict[player_id]['full_name']] = player_id

		if players_dict[player_id]['position'].lower() == position and ('pts_ppr' if position != 'def' else 'pts_std') in stats[player_id]:
			stats_list.append((player_id, stats[player_id]))
			POSITION_POINTS_DICT[week][position.upper()].append(stats[player_id]['pts_ppr' if position != 'def' else 'pts_std'])

	stats_list = sorted(stats_list, key=sortPlayers, reverse=True)
	stats_list_names = [players_dict[d[0]][('full_name' if position != 'def' else 'last_name')] for d in stats_list]

	printRankings(top_n_to_print, stats_list_names)

	return (stats_list, stats_list_names)

def printRankings(limit, l, reverseRank=False, parenMessage=""):
	l = list(l)
	for rank, item in enumerate(l, start=1):
		if rank > limit:
			break

		rank_print = rank if not reverseRank else len(l) + 1 - rank
		if len(item) == 1:
			print("{})\t{}".format(rank_print, getStringInColor(Fore.RED, item)))
		else:
			print("{})\t{} ({} {})".format(rank_print, getStringInColor(Fore.RED, item[0]), parenMessage, item[1]))

def getStringInColor(color, s):
	return "{}{}{}".format(color, s, Style.RESET_ALL)

def getPercentile(l, n):
	for i, val in enumerate(l):
		if i == len(l) - 1: # Reached the end of the list, so this must be the last item.
			return 100

		if n >= val and n <= l[i+1]:
			return (i * 100) / len(l)

def normalizePlayerName(s):
	split = s.split()
	if len(split) == 2:
		first, last = split
	elif len(split) == 3:
		first, last, _ = split
	else:
		print(getStringInColor(Fore.YELLOW, "Warning: weird name to split -> {}".format()))
		return s

	if first == "DJ": first = "D.J."
	if first == "DK": first = "D.K."
	if last == "Trubisky": first = "Mitch"
	if first in ["OJ", "O.J."] and last == "Howard": first = "O.J."
	# if extra in ["Jr.", "Sr.", "II", "III", "IV", "V"]: extra = 

	return "{} {}".format(first, last)

def getDashedString(n=100, lines=1, color=Fore.GREEN):
	s = ""
	for _ in range(lines):
		s += ("-" * n)
		s += "\n"

	return getStringInColor(color, s.strip())

def getCumulativeRankings(weeks=None, positions=None):
	weeks = list(range(1, getCurrentWeek()+1) if not weeks else (range(int(weeks.split("-")[0]), int(weeks.split("-")[1])+1)) if "-" in weeks else range(int(weeks.split("-")[0]), int(weeks.split("-")[0])+1))
	positions = list(ALL_POSITIONS_LIST) if positions == '' else positions.lower().split(",")

	print("\n")
	option = getValidInput("\nPer-game average (pg) or cumulative (c)? ", lambda x: x.lower() in ["pg", "c"])
	print("\n")

	for pos in positions:
		print("\n" + getStringInColor(Fore.YELLOW, pos.upper() + "s"))
		position_pts_dict = dict()
		for wk in weeks:
			stats, names = getPositionResults(pos, wk)
			for player_id, player_stats in stats:
				weeks_pts = player_stats['pts_ppr' if 'pts_ppr' in player_stats else 'pts_std']
				if option == "c":
					if player_id not in position_pts_dict: position_pts_dict[player_id] = 0
					position_pts_dict[player_id] += weeks_pts
				else:
					if player_id not in position_pts_dict: position_pts_dict[player_id] = list()
					position_pts_dict[player_id].append(weeks_pts)

		if option == "pg":
			position_pts_dict = {k: v for (k, v) in position_pts_dict.items() if len(v) >= 3} # 3-game minimum for per-game averages.
			for player_id in position_pts_dict:
				position_pts_dict[player_id] = (average(position_pts_dict[player_id]), len(position_pts_dict[player_id]))

		positions_pts_list = sorted(position_pts_dict, key=position_pts_dict.get, reverse=True)
		for i, player_id in enumerate(positions_pts_list[:15], start=1):
			if option == "c":
				print("\t{}) {} -> {} pts".format(i, players_dict[player_id][('full_name' if pos != 'def' else 'last_name')], position_pts_dict[player_id]))
			else:
				print("\t{}) {} -> {} average pts ({} games)".format(i, players_dict[player_id][('full_name' if pos != 'def' else 'last_name')], position_pts_dict[player_id][0], position_pts_dict[player_id][1]))
		
		if pos != positions[-1]:
			_ = input("")

def getValidInput(prompt, test):
	user = re.sub(r"\s+", "", input(prompt)).lower()
	while not test(user):
		print("Invalid input. Please try again.\n")
		user = re.sub(r"\s+", "", input(prompt)).lower()

	return user

def getCurrentWeek():
	d1 = date(2019, 9, 8) # Sunday of week 1.
	d2 = date.today()
	return ((d2-d1).days // 7) + 1


########################################## MAIN ##########################################

if __name__ == "__main__":

	init() # Initialize colorama.

	with warnings.catch_warnings(): # Catch the RuntimeWarning given by Scipy.
		warnings.simplefilter("ignore")
		fxn()

		for _ in range(2):
			try:
				with open("players_fixed.json") as json_file:
					players_dict = json.load(json_file)
					break
			except:
				fixJsonFile()

		if len(sys.argv) == 2 and sys.argv[1] == "rankings":
			weeks_response = getValidInput("Enter the week or range of weeks (separated by a dash) that you want to see cumulative rankings for. Press enter to include everything: ",
				lambda x: all([char.isdigit() or char == '-' for char in x]))
			positions_response = getValidInput("Enter the position(s) (separated by commas) that you want to see cumulative rankings for. Press enter to include everything: ",
				lambda x: all([char.isalpha() or char == ',' for char in x]))
			
			getCumulativeRankings(weeks_response, positions_response)
			sys.exit()


		weeks_response = getValidInput("Enter the week or range of weeks (separated by a dash) that you want analyzed. Press enter to include everything: ",
			lambda x: all([char.isdigit() or char == '-' for char in x]))

		skip_response = getValidInput("Do you want to skip straight to the cumulative results (y/n)? ",
			lambda x: x.lower() in ["y", "n"])
		skip_to_cumulative = (skip_response == 'y')

		if not skip_to_cumulative:
			lh_response = getValidInput("Do you want to see per-player results for love/hate (y/n)? ",
				lambda x: x.lower() in ["y", "n"])
			show_lh_players = (lh_response == "y")

		if "-" in weeks_response:
			start_week, end_week = int(weeks_response.split("-")[0]), int(weeks_response.split("-")[1])
		else:
			if weeks_response.strip() != "":
				start_week = end_week = int(weeks_response)
			else:
				start_week, end_week = 3, getCurrentWeek() # Start week is 3 because I started copying the rankings too late.

		if start_week < 3:
			print(getStringInColor(Fore.YELLOW, "Warning: Changing the first week to 3 because that's the earliest rankings data available."))
			start_week = 3
		if end_week > getCurrentWeek():
			print(getStringInColor(Fore.YELLOW, "Warning: Changing the last week to {} because that's the most current week so far.".format(getCurrentWeek())))
			end_week = getCurrentWeek()

		results_dict = dict() # Maps from position group to weekly results.
		players_results_dict = dict() # Maps from position to player name to weekly results.
		love_hate_dict = dict() # Maps from player name to week to love/hate results.
		total_love_correct = total_love_total = total_hate_correct = total_hate_total = 0


		##### Let's do some analysis boiiii #####

		for current_week in range(start_week, end_week + 1):
			if not skip_to_cumulative and current_week != start_week:
				_ = input("\n")

			if not skip_to_cumulative:
				print("\n\n" + getDashedString(color=Fore.MAGENTA) + "\n")

			response = requests.get("https://api.sleeper.app/v1/stats/nfl/regular/2019/{}".format(current_week))
			stats = response.json()

			### First, compare rankings to actual performances for each position group.
			for position in ALL_POSITIONS_LIST:
				if position not in players_results_dict: players_results_dict[position] = dict()

				file_path = "week{}/{}.txt".format(current_week, position)
				if not os.path.exists(file_path):
					print("\nNo rankings file found for {}s in week {}...skipping.".format(position.upper(), current_week))
					continue

				# Extract the predicted rankings from the position's rankings file.
				with open(file_path) as position_rankings_file:
					rankings_list = list()

					# Iterate through the lines of rankings and extract each player name.
					text = position_rankings_file.readlines()
					for i in range(0, len(text), 2):
						match = re.search(r'[0-9]\. (.*), ', text[i])
						if match:
							rankings_list.append(normalizePlayerName(match.group(1)))
							if position == 'def':
								rankings_list[-1] = rankings_list[-1].replace(" D/ST", "")

				# Then compile a sorted list of player's actual performances in the given week.
				stats_list, stats_list_names = getPositionResults(position, current_week, stats)

				# Add up the differences between predicted and real rankings.
				difference_sum = 0
				for rank, p in enumerate(stats_list_names, start=1):
					if p in rankings_list:
						difference_sum += abs((rankings_list.index(p) + 1) - rank)

				# To make sure the coefficient works, only include the players that the two lists have in common.
				rankings_list_common = [p for p in rankings_list if p in stats_list_names]
				stats_list_names_common = [p for p in stats_list_names if p in rankings_list_common]
				assert(len(rankings_list_common) == len(set(rankings_list_common)))

				for p in rankings_list_common:
					if p not in players_results_dict[position]:
						players_results_dict[position][p] = dict()
					if current_week not in players_results_dict[position][p]:
						players_results_dict[position][p][current_week] = abs(rankings_list_common.index(p) - stats_list_names_common.index(p))

				# Calculate the Kendall coefficient and the average difference between predicted and real rankings for
				# this position group in this week.
				coef, p = kendalltau(rankings_list_common, stats_list_names_common)
				coef = abs(coef)
				avg_difference = difference_sum / (pow(len(rankings_list_common), 2))

				if not skip_to_cumulative:
					print("\nResults for {} in week {} (# players = {}):".format(getStringInColor(Fore.YELLOW, position.upper() + "s"), current_week, len(rankings_list_common)))
					print("\t\tKendall's correlation coefficient: {}".format(getStringInColor(Fore.GREEN, str(coef)[:5])))
					print("\t\tThe average difference score between predicted and real rankings was {}.".format(getStringInColor(Fore.GREEN, avg_difference)))

				if position not in results_dict: results_dict[position] = dict()
				if current_week not in results_dict[position]: results_dict[position][current_week] = dict()

				results_dict[position][current_week]['coefficient'] = coef
				results_dict[position][current_week]['avg_difference'] = avg_difference

			### Second, compare Berry's love/hate to actual performances.
			file_path = "week{}/love_hate.txt".format(current_week)
			if not os.path.exists(file_path):
				print("\nNo rankings file found for {}s in week {}...skipping.".format(position.upper(), current_week))
				continue

			with open(file_path) as lh_file:

				if not skip_to_cumulative:
					print("\n\nMatthew Berry's love/hate results for week {}:\n".format(current_week))

				love_hate_position_list = ['QB', 'RB', 'WR', 'TE']
				love_hate_string = ""
				love_hate_pos = ""

				for position in love_hate_position_list:
					POSITION_POINTS_DICT[current_week][position] = sorted(POSITION_POINTS_DICT[current_week][position])

				for line in lh_file.readlines():
					if line.strip() == '': continue

					position, lh, full_name = map(str.strip, line.split("/"))
					full_name = normalizePlayerName(full_name)

					if full_name not in PLAYER_ID_CACHE:
						if not skip_to_cumulative:
							print(getStringInColor(Fore.YELLOW, "\nWarning: {} not found in cache\n".format(full_name)))
						continue

					player_id = PLAYER_ID_CACHE[full_name]
					if player_id not in stats or 'pts_ppr' not in stats[player_id]:
						if not skip_to_cumulative:
							print(getStringInColor(Fore.YELLOW, "\nWarning: {} doesn't have stats for week {}\n".format(full_name, current_week)))
						continue

					percentile = getPercentile(POSITION_POINTS_DICT[current_week][position], stats[player_id]['pts_ppr'])

					if full_name not in love_hate_dict: love_hate_dict[full_name] = dict()


					prediction_was_correct = (lh == 'L' and percentile >= 67) or (lh == 'H' and percentile <= 33)
					love_hate_dict[full_name][current_week] = (position, lh, prediction_was_correct)

					if not skip_to_cumulative and show_lh_players:
						if position != love_hate_pos:
							print("{}:".format(getStringInColor(Fore.YELLOW, position)))
						love_hate_pos = position

						if lh != love_hate_string:
							print("\t{}:".format("love" if lh == 'L' else "hate"))
						love_hate_string = lh
						
						print(getStringInColor(Fore.GREEN if prediction_was_correct else Fore.RED,
							"\t\t\t{}: {} pts ({} percentile)".format(
							full_name,
							stats[player_id]['pts_ppr'],
							percentile)))
				
				if not skip_to_cumulative and show_lh_players:
					print("\n")

				for position in love_hate_position_list:
					
					love_correct = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week] == (position, 'L', True)])
					love_total = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][0] == position and love_hate_dict[p][current_week][1] == 'L'])
					hate_correct = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week] == (position, 'H', True)])
					hate_total = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][0] == position and love_hate_dict[p][current_week][1] == 'H'])
					
					if not skip_to_cumulative and love_total + hate_total > 0:
						print("\tHe hit on {} (out of {}) {} loves and {} (out of {}) hates ({} correct in total)".format(
							getStringInColor(Fore.GREEN, love_correct),
							getStringInColor(Fore.RED, love_total),
							getStringInColor(Fore.YELLOW, position),
							getStringInColor(Fore.GREEN, hate_correct),
							getStringInColor(Fore.RED, hate_total),
							getStringInColor(Fore.GREEN, str(((love_correct + hate_correct) * 100) / (love_total + hate_total))[:5] + "%")))

				love_correct = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][1:] == ('L', True)])
				love_total = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][1] == 'L'])
				hate_correct = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][1:] == ('H', True)])
				hate_total = len([1 for p in love_hate_dict if current_week in love_hate_dict[p] and love_hate_dict[p][current_week][1] == 'H'])

				total_love_correct += love_correct
				total_love_total += love_total
				total_hate_correct += hate_correct
				total_hate_total += hate_total

				if not skip_to_cumulative:
					print("\n")
					print("\tIn total, he hit on {} loves out of {} ({}%)".format(
						getStringInColor(Fore.GREEN, love_correct),
						getStringInColor(Fore.RED, love_total), 
						getStringInColor(Fore.GREEN, str((love_correct * 100) / love_total))))
					print("\tIn total, he hit on {} hates out of {} ({}%)".format(
						getStringInColor(Fore.GREEN, hate_correct),
						getStringInColor(Fore.RED, hate_total), 
						getStringInColor(Fore.GREEN, str((hate_correct) * 100 / hate_total))))

		

		##################### Afterwards, calculate and display cumulative results if desired. #####################

		if skip_to_cumulative:
			cumulative_response = 'y'
		else:
			cumulative_response = getValidInput("\n\n\nDo you want to see the cumulative results? (y/n): ",
				lambda x: x in ["y", "n"])

		if cumulative_response == 'y':
			print("\n\n" + getDashedString(lines=2, color=Fore.YELLOW) + "\n\n")
			print("These are the cumulative results using {}:".format(
				"week {}".format(start_week) if start_week == end_week else "weeks {}-{}".format(start_week, end_week)))
			
			cumulative_list = list()

			for position in results_dict:
				# Analyze the position group's prediction results overall first.
				print("\n\n{}{}s{}:".format(Fore.YELLOW, position.upper(), Style.RESET_ALL))

				avg_coefficient = average([results_dict[position][week]['coefficient'] for week in results_dict[position]])
				print("\tAverage coefficient: {}".format(getStringInColor(Fore.GREEN, str(avg_coefficient)[:5])))

				avg_avg_difference = average([results_dict[position][week]['avg_difference'] for week in results_dict[position]])
				print("\tAverage of average differences: {}".format(getStringInColor(Fore.GREEN, str(avg_avg_difference)[:5])))
				
				cumulative_list.append((position.upper(), avg_coefficient, avg_avg_difference))

				# Then analyze individual players within the position group.
				p_results_list = list()
				for p in players_results_dict[position]:
					p_results_list.append((p, average([players_results_dict[position][p][week] for week in players_results_dict[position][p]])))
				p_results_list = sorted(p_results_list, key=lambda x: x[1])

				print("\nThe 3 most predictable {}s were:".format(position.upper()))
				printRankings(3, p_results_list, parenMessage="average difference from correct rank:")

				print("\nThe 3 most unpredictable {}s were:".format(position.upper()))
				printRankings(3, p_results_list[::-1], reverseRank=True, parenMessage="average difference from correct rank:")


			cumulative_list = sorted(cumulative_list, key=lambda x: x[2])
			print("\n\nHere are the position groups, ranked from most predictable to least predictable:")
			for i, pos in enumerate(cumulative_list, start=1):
				print(str(i) + ") " + getStringInColor(Fore.YELLOW, pos[0]))
			# print("\n\nThe most predictable position group was: {}".format(getStringInColor(Fore.YELLOW, cumulative_list[0][0])))
			# print("\nThe most unpredictable position group was: {}".format(getStringInColor(Fore.YELLOW, cumulative_list[-1][0])))

			print("\n\n")
			print("In total, Berry hit on {} loves out of {} ({}%)".format(
						getStringInColor(Fore.GREEN, total_love_correct),
						getStringInColor(Fore.RED, total_love_total),
						getStringInColor(Fore.GREEN, str((total_love_correct * 100) / total_love_total))))
			print("In total, Berry hit on {} hates out of {} ({}%)".format(
						getStringInColor(Fore.GREEN, total_hate_correct),
						getStringInColor(Fore.RED, total_hate_total), 
						getStringInColor(Fore.GREEN, str((total_hate_correct) * 100 / total_hate_total))))

			# TODO: Check which players were loved the most and hated the most. How accurate was he on each?

			# TODO: Rank the weeks from best to worst predicted.