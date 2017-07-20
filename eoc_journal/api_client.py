"""
A wrapper around the Edx API.
"""

from django.conf import settings

import requests


# Points for social activities
SOCIAL_METRICS_POINTS = {
    'num_threads': 10,
    'num_comments': 15,
    'num_replies': 15,
    'num_upvotes': 25,
    'num_thread_followers': 5,
    'num_comments_generated': 15,
}

PROGRESS_IGNORE_COMPONENTS = [
    'discussion-course',
    'group-project',
    'discussion-forum',
    'eoc-journal',

    # GP v2 categories
    'gp-v2-project',
    'gp-v2-activity',
    'gp-v2-stage-basic',
    'gp-v2-stage-completion',
    'gp-v2-stage-submission',
    'gp-v2-stage-team-evaluation',
    'gp-v2-stage-peer-review',
    'gp-v2-stage-evaluation-display',
    'gp-v2-stage-grade-display',
    'gp-v2-resource',
    'gp-v2-video-resource',
    'gp-v2-submission',
    'gp-v2-peer-selector',
    'gp-v2-group-selector',
    'gp-v2-review-question',
    'gp-v2-peer-assessment',
    'gp-v2-group-assessment',
    'gp-v2-static-submissions',
    'gp-v2-static-grade-rubric',
    'gp-v2-project-team',
    'gp-v2-navigator',
    'gp-v2-navigator-navigation',
    'gp-v2-navigator-resources',
    'gp-v2-navigator-submissions',
    'gp-v2-navigator-ask-ta',
    'gp-v2-navigator-private-discussion',
]


def calculate_engagement_score(social_metrics):
    """
    Calculates and returns the total score for the given social metrics
    """
    engagement_total = 0

    for key, val in SOCIAL_METRICS_POINTS.iteritems():
        engagement_total += social_metrics.get(key, 0) * val
    return engagement_total


def course_components_ids(course, ignored_categories):
    """
    Returns list of course components, excluding components of ignored
    categories.
    """
    def filter_children(children):
        """Returns list of children filtered out by category. """
        return [c['id'] for c in children if c['category'] not in ignored_categories]

    components = []
    for lesson in course['chapters']:
        for sequential in lesson['sequentials']:
            for page in sequential['pages']:
                if 'children' in page:
                    children = filter_children(page['children'])
                    components.extend(children)
    return components


def _get_edx_api_key():
    """
    Returns the EDX_API_KEY from the django settings.
    If key is not set, returns None.

    This key should never be sent to the client, as it is only used to
    communicate with the api server.
    """
    if hasattr(settings, 'EDX_API_KEY'):
        return settings.EDX_API_KEY
    return None


def get(url, params=None):
    """
    Sends a GET request to the URL and returns the parsed JSON response.
    """
    key = _get_edx_api_key()

    if key:
        headers = {'X-Edx-Api-Key': key}
        return requests.get(url, headers=headers, params=params).json()
    return None


class ApiClient(object):
    """
    Object builds an API client to make calls to the LMS user API.
    """

    def __init__(self, user, course_id):
        """
        Connect to the REST API.
        """
        self.user = user
        self.course_id = course_id

        # pylint: disable=C0103
        if hasattr(settings, 'LMS_ROOT_URL'):
            self.API_BASE_URL = settings.LMS_ROOT_URL + '/api/server'
        else:
            self.API_BASE_URL = None

    def get_user_engagement_metrics(self):
        """
        Fetches and returns social metrics for the current user in the
        specified course.
        """
        url = '{base_url}/users/{user_id}/courses/{course_id}/metrics/social/'.format(
            base_url=self.API_BASE_URL,
            user_id=self.user.id,
            course_id=self.course_id,
        )

        return get(url)

    def get_cohort_engagement_metrics(self):
        """
        Fetches the cohort engagement points, calculates and returns the
        average.
        """
        url = '{base_url}/courses/{course_id}/metrics/social/'.format(
            base_url=self.API_BASE_URL,
            course_id=self.course_id,
        )

        return get(url)

    def _get_course_completions(self):
        """
        Fetches and returns the user's completed modules within the course.
        """
        params = {'page_size': 0, 'user_id': self.user.id}
        url = '{base_url}/courses/{course_id}/completions'.format(
            base_url=self.API_BASE_URL,
            course_id=self.course_id,
        )
        return get(url, params=params)

    def _get_course(self):
        """
        Fetches and returns chapters, sequentials, and pages information about
        the current course.
        """
        params = {'depth': 5}

        # IMPORTANT: This requires that no trailing / be provided.
        url = '{base_url}/courses/{course_id}'.format(
            base_url=self.API_BASE_URL,
            course_id=self.course_id,
        )

        return get(url, params=params)

    def _get_completion_leader_metrics(self):
        """
        Fetches and returns user completion metrics.
        """
        params = {
            'skipleaders': True,
            'user_id': self.user.id,
        }

        url = '{base_url}/courses/{course_id}/metrics/completions/leaders/'.format(
            base_url=self.API_BASE_URL,
            course_id=self.course_id,
        )

        return get(url, params=params)

    def get_user_progress(self):
        """
        Calculates the progress percentage for the current user.
        """
        completions = self._get_course_completions()
        course = self._get_course()

        if completions is None or course is None:
            return None

        completed_ids = [result['content_id'] for result in completions]

        chapters = [
            module
            for module in course['content'] if module['category'] == 'chapter'
        ]

        for chapter in chapters:
            chapter['sequentials'] = [
                child for child in chapter['children'] if child['category'] == 'sequential'
            ]
            for sequential in chapter['sequentials']:
                sequential['pages'] = [
                    child for child in sequential['children'] if child['category'] == 'vertical'
                ]
        course['chapters'] = chapters

        components_ids = course_components_ids(course, PROGRESS_IGNORE_COMPONENTS)
        actual_completions = set(components_ids).intersection(completed_ids)

        try:
            return round(float(100 * len(actual_completions)) / len(components_ids))
        except ZeroDivisionError:
            return 0

    def get_cohort_average_progress(self):
        """
        Fetches and returns cohort average progress.
        """
        data = self._get_completion_leader_metrics()

        if data:
            return data.get('course_avg', None)
        return None