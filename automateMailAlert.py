#
# coding: utf-8


"""
Objectif du script:
Envoyer en 1 mail (quelque soit le nombre d'automate et le nombre de compte) les informations relatives au calcul
du pivot, Le but premier de ce mail est de pouvoir constater tout de suite grace a un programme exterieur a
l'automate si le calcul du pivot ou la lecture du pivot se sont bien passés, le cas échéant pouvoir agir
manuellement.

Utilisation du script:
Ce script est appelé 2 fois dans la journée grace au task scheduler, une fois le matin avant le passage de l'ordre
avec un parametre 'matin', et une fois le soir apres le calcul du pivot avec le parametre 'soir'. Ces 2 parametres
sont essentiels car ce sont eux qui permettent de savoir s'il s'agit d'une lecture de pivot ou d'un calcul de pivot


"""

import smtplib
import logging
import os.path
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


logging.basicConfig(format='%(asctime)s: %(message)s',
					datefmt='%Y/%m/%d %I:%M:%S',
					level=logging.INFO,
					filename="mail.log")

config = {
	'mail': {
		'sender': '',
		'recipient': [''],
		'host': '',
		'port': ,
		'login': '',
		'pw': ''
	},
	# tous les comptes qu'on veut suivre sont à ajouter à cette liste
	'info_cptes': [
		{
			'path_to_pivot': '',
			'num_cpte': '',
			'nom_ptf': '',
			'ptf': []
			
		}
	],
	# permet d'empeche que le suite se poursuive si l'un des 2 parametres n'est pas présent en CL
	'acceptable_periods': ['matin', 'soir']

}


def sendMail(subj, mess, conf):
	""" envoyer un mail avec du contenu html, les config sont a ajuster en fonction des differents parametres """

	msg = MIMEMultipart()
	msg['From'] = conf['sender']
	msg['To'] = ','.join(conf['recipient'])
	msg['Subject'] = subj

	msg.attach(MIMEText(mess, 'html'))
	mailserver = smtplib.SMTP(conf['host'], conf['port'])
	mailserver.ehlo()
	mailserver.starttls()
	mailserver.ehlo()
	mailserver.login(conf['login'], conf['pw'])
	mailserver.sendmail(conf['sender'], conf['recipient'], msg.as_string())

	mailserver.quit()


def buildPivotPath(devise, path):
	""" permet de construire le nom du fichier à recup histo%DEVISE%, et de le joindre a son repertoire"""
	fname = 'pivot' + devise.upper()
	return os.path.join(path, fname)


def readPivotFile(path_):
	""" lit uniquement la 1ere ligne du pivot et retourne un tableau contenant les entrées du pivot """
	with open(path_, 'r') as fd:
		line = fd.readlines()[0]
		info_piv = line.split(";")

	return info_piv


def buildHead():
	""" Lit un fichier html et constitue l'en tete de notre string html qu'on va envoyer au mail """
	with open("head.html", "r") as fd:
		return fd.read()


def buildTable(cpte_rendu, num_cpte, periode):
	""" construit le tableau html, 1 tableau pour chaque compte, à noter que le dernier élement est un tuple
	contenant une couleur et un string appelé dans buildSummary """
	lect_or_calc = 'Date Calcul' if periode == 'soir' else 'Date Lecture'

	table = '<h3>Compte {}</h3>'.format(num_cpte)
	table += '<table><thead>' \
		   '<th>Devise</th><th>Date du jour</th><th>{}</th><th>Valeur</th><th>Etat</th>' \
		   '</thead><tbody>'.format(lect_or_calc)

	for line_dev in cpte_rendu:
		table += '<tr>'

		# on s'arrete juste avant le tuple (class, string)
		for elt in line_dev[:-1]:
			table += '<td>{}</td>'.format(elt)
		table += '<td class="{}">{}</td>'.format(line_dev[-1][0], line_dev[-1][1])
		table += '</tr>'

	table += '</tbody></table><hr/>'

	return table


def buildSummary(date, devises, info_cpte, periode):
	""" Construit le contenu du compte rendu puis le passe a buildTable qui va le mettre sous la forme html
	retourne ensuite le nb d'erreur qui determinera si la categorie du mail est INFO (0 erreur) ou
	URGENT(>0 erreur ) et le corps du message html pour un compte, buildSummary est appelée autant de fois
	qu'il y a de compte """

	nb_error, nb_ordres_lus = 0, 0
	compte_rendu = []
	for dev in devises:
		try:
			pivot_path = buildPivotPath(dev, info_cpte['path_to_pivot'])
			date_calcul_piv, date_lect_piv, val_piv = readPivotFile(pivot_path)

			# On choisit la date a vérifier adaptée a la periode (LECTURE OU CALCUL)
			date_a_verifier = date_calcul_piv if periode == 'soir' else date_lect_piv
			logging.info("date_a_verifier: {}".format(date_a_verifier))
			logging.info("periode dans buildSummary: {}".format(periode))

			# on verifie que le pivot est bien lu le jour meme
			is_ok = (True if date_a_verifier == date else False)

			if is_ok:
				msg_str = 'OK'
				class_ = 'success'
			else:
				nb_error += 1
				msg_str = 'ERREUR'
				class_ = 'error'

			compte_rendu.append([dev.upper(), date, date_a_verifier, val_piv, (class_, msg_str)])
			nb_ordres_lus += 1

		except Exception as e:
			logging.error(str(e))
			# si jamais l'ordre n'a pas été noté dans le fichier pivot, on ajoute quand meme une ligne vide
			nb_error += 1
			compte_rendu.append([dev.upper(), '', '', '', ('error', 'ERREUR')])

	logging.info('compte-rendu: {}'.format(compte_rendu.__str__()))
	body = buildTable(compte_rendu, info_cpte['num_cpte'], periode)

	return body, nb_error


def verifierPivot(date, conf):
	""" fonction principale du script, genere un string html  et appelle autant de fois buildSummary
	qu'il y a de compte dans les config puis envoie le mail """
	body = buildHead()
	body += '<h1 style="text-align: center">{}</h1><hr/>'.format(date)
	tot_errors = 0

	for info_cpte in conf['info_cptes']:
		table, nb_errors = buildSummary(date, info_cpte['ptf'], info_cpte, conf['period'])
		tot_errors += nb_errors
		body += table

	# si on a repéré une erreur dans l'un des comptes tot_error > 0 -> categorie URGENT
	category = 'URGENT' if tot_errors > 0 else 'INFO'
	titre = 'CALCUL PIVOT' if conf['period'].lower() == 'soir' else 'LECTURE PIVOT'
	sujet = '{}: {}'.format(category, titre)

	return (sujet, body)
	

def getArgsCL(accept_periods):
	""" recuperer l'argument pour savoir si on doit vérifier la lecture ou le calcul du pivot """

	periode = sys.argv[1]
	if periode not in accept_periods:
		error = 'La periode demandée n\'existe pas, Se référer aux configs pour plus d\'info sur les périodes'
		raise Exception(error)

	return periode


def isWeekend(day=None):
	# 5 = samedi, 6 = dimanche
	weekend = (5, 6)
	if day is None:
		day = datetime.now()

	return day.weekday() in weekend


if __name__ == '__main__':
	today = datetime.now()

	# ce programme ne doit pas fonctionner le samedi et le dimanche
	if isWeekend(today):
		sys.exit(0)

	config['period'] = getArgsCL(config['acceptable_periods'])
	logging.info("dans main, periode: {}".format(config['period']))
	today_str = today.strftime("%Y/%m/%d")
	outcome, details_pivots = verifierPivot(today_str, config)

	try:
		sendMail(outcome, details_pivots, config['mail'])

	except Exception as e:
		logging.error(e)
