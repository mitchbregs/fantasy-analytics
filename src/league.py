import json
import logging
import requests

from .constants import (
    FBA_ENDPOINT,
    STATS_INT_TO_STRING
)

from .utils.http_util import request_status
from .utils.json_util import get_nested
from .utils.object_util import _cast_none

logging.basicConfig(level='INFO')
logger = logging.getLogger(__name__)


class League(object):
    """Get league instance from ESPN"""
    def __init__(self, league_id: int, year: int, team_id: int, cookies, debug=False):
        self.cookies = cookies
        if not self.cookies:
            logger.error('No Authorization Credentials')
            raise ValueError('No Authorization Credentials')
        self.league_id = league_id
        self.year = year
        self.team_id = team_id
        self.meta = self._fetch_league_meta()

    def __repr__(self):
        return f'<League `{self.league_id}` {self.year}>'

    def _fetch_league_meta(self):

        url = f'{FBA_ENDPOINT}{self.year}/segments/0/leagues/{self.league_id}'
        resp = requests.get(url=url, cookies=self.cookies)

        # raise error if bad response
        request_status(resp.status_code)

        data = resp.json()

        members = [{'id': x['id'], 'name': x['displayName']} for x in data['members']]
        teams = [
            {'id': x['id'], 'owner': x['owners'][0], 'name': x['nickname']}
            for x in data['teams']
        ]

        meta = {
            'current_week': data['status']['currentMatchupPeriod'],
            'nba_day': data['status']['latestScoringPeriod'],
            'members': members,
            'teams': teams
        }

        logger.info(f'League Data: {json.dumps(meta, indent=4)}')

        return meta


    def _fetch_team_meta(self, team_id=None):

        team_id = team_id if team_id is not None else self.team_id

        params = {
            'view': 'mTeam'
        }
        url = f'{FBA_ENDPOINT}{self.year}/segments/0/leagues/{self.league_id}'
        resp = requests.get(url=url, params=params, cookies=self.cookies)

        request_status(resp.status_code)

        # raise error if bad response
        teams = resp.json()['teams']

        ## fantasy team ids start at 1 not 0
        my_team = teams[team_id-1]

        team_meta = {
            'id': team_id,
            'abbrev': my_team['abbrev'],
            'owner': my_team['primaryOwner'],
            'name': my_team['nickname'],
            'record': (
                my_team['record']['overall']['wins'],
                my_team['record']['overall']['losses'],
                my_team['record']['overall']['ties']
            ),
            'stats': my_team['valuesByStat']
        }

        logger.info(f'My Team Data: {json.dumps(team_meta, indent=4)}')

        return team_meta


    def _fetch_rosters(self, team_id=None):

        params = {
            'view': 'mRoster',
            'scoringPeriod': self.meta['current_week']
        }

        url = f'{FBA_ENDPOINT}{self.year}/segments/0/leagues/{self.league_id}'
        resp = requests.get(url=url, params=params, cookies=self.cookies)

        request_status(resp.status_code)

        data = resp.json()

        ## make more efficient
        rosters = {}
        for team in data['teams']:
            rosters[team['id']] = []
            for player in team['roster']['entries']:
                rosters[team['id']].append((
                    player['playerId'],
                    player['playerPoolEntry']['player']['fullName']
                ))

        return rosters

    def _fetch_stats(self):
        league_stats = []

        rosters = self.rosters

        for roster in rosters:
            entries = roster['roster'].get('entries')

            team_stats = []
            for player in entries:
                stats = get_nested(player, 'playerPoolEntry.player.stats')

                for statline in stats:
                    if statline.get('statSplitTypeId') == 2:
                        season_totals = statline.get('stats')

                        relevant_items = dict((STATS_INT_TO_STRING[k], v) for (k, v) in season_totals.items()
                                              if k in STATS_INT_TO_STRING.keys())

                        teams = self._fetch_teams()
                        idx = roster.get('id')
                        team_name = [x['nickname'] for x in teams['teams'] if x['id'] == idx][0].strip()

                        player_metadata = {
                            'teamId': team_name,
                            'name': get_nested(player, 'playerPoolEntry.player.fullName'),
                            'id': get_nested(player, 'playerPoolEntry.player.id'),
                            'stats': {
                                'points': _cast_none(relevant_items.get('points')),
                                'blocks': _cast_none(relevant_items.get('blocks')),
                                'steals': _cast_none(relevant_items.get('steals')),
                                'assists': _cast_none(relevant_items.get('assists')),
                                'rebounds': _cast_none(relevant_items.get('rebounds'))
                            }
                        }

                        team_stats.append(player_metadata)
                        logger.info(f'Team Stats: {player_metadata}')

            league_stats.append(team_stats)

        return league_stats

    def _calculate_totals(self, team_id=None):
        roster_stats = self.roster_stats

        team_totals = []
        for roster in roster_stats:
            stat_totals = {
                'teamId': roster[0].get('teamId'),
                'points': sum(d['stats'].get('points') for d in roster),
                'blocks': sum(d['stats'].get('blocks') for d in roster),
                'steals': sum(d['stats'].get('steals') for d in roster),
                'assists': sum(d['stats'].get('assists') for d in roster),
                'rebounds': sum(d['stats'].get('rebounds') for d in roster),
            }

            logger.info(f'Team Statistics Totals: {stat_totals}')
            team_totals.append(stat_totals)

        if not team_id:
            return team_totals
        else:
            team_id_totals = [x for x in team_totals if x.get('teamId') == team_id]
            return team_id_totals

