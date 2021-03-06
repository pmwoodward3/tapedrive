from django.db.transaction import atomic
from django.shortcuts import redirect, reverse
from django.shortcuts import get_object_or_404
from django.contrib.sites.shortcuts import get_current_site
from django.views.decorators.http import require_POST
from django.http import (
    HttpResponseBadRequest, JsonResponse,
    HttpResponseForbidden, HttpResponse
)

from django.template.defaultfilters import date as _date
from django.utils.formats import get_format
from django.core.serializers import serialize

import copy
import requests
from datetime import datetime
from urllib.parse import urlparse, urlunparse, urlencode

from podcasts.models.listener import EpisodePlaybackState, Listener
from podcasts.models.podcast import Podcast
from podcasts.models.episode import Episode
from podcasts.utils import unify_apple_podcasts_response, HEADERS
from podcasts.serializers import EpisodeSerializer
from podcasts import utils
from podcasts.conf import (ITUNES_TOPCHARTS_URL, ITUNES_LOOKUP_URL, ITUNES_SEARCH_URL, ITUNES_SEARCH_LIMIT)

from rest_framework.generics import RetrieveAPIView


class HttpResponseNoContent(HttpResponse):
    status_code = 204


def encode_datetime(obj):
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%dT%H:%M:%S%z')
    raise TypeError(repr(obj) + " is not JSON serializable")


@require_POST
def podcast_add(request):
    feed_url = request.POST.get('feed_url')
    feed_id = request.POST.get('feed_id')
    if not feed_url and not feed_id:
        return HttpResponseBadRequest()

    if feed_url:
        podcast, created = Podcast.objects.get_or_create_from_feed_url(feed_url, only_first_page=True)
    elif feed_id:
        podcast, created = Podcast.objects.get_or_create_from_itunes_id(feed_id, only_first_page=True)
    podcast.add_subscriber(request.user.listener)
    podcast.add_follower(request.user.listener)

    return JsonResponse({'created': created, 'url': podcast.get_absolute_url()})


def podcast_add_from_id(request, id):
    podcast, created = Podcast.objects.get_or_create_from_itunes_id(id, only_first_page=True)
    podcast.add_subscriber(request.user.listener)
    podcast.add_follower(request.user.listener)

    return JsonResponse({'created': created, 'url': podcast.get_absolute_url()})


def podcast_refresh_feed(request, slug=None):
    podcast = get_object_or_404(Podcast, slug=slug)
    response_data = {}
    response_data['info'] = podcast.update(update_all=True)

    return JsonResponse(response_data)


def podcast_subscribe(request, slug=None):
    if request.user is None:
        return HttpResponseForbidden
    podcast = get_object_or_404(Podcast, slug=slug)
    podcast.add_subscriber(request.user.listener)
    podcast.save()
    return HttpResponseNoContent()


def podcast_unsubscribe(request, slug=None):
    if request.user is None:
        return HttpResponseForbidden()
    podcast = get_object_or_404(Podcast, slug=slug)
    podcast.remove_subscriber(request.user.listener)
    podcast.save()
    return HttpResponseNoContent()


@atomic
@require_POST
def episodes_mark_played(request, id):
    object = get_object_or_404(Episode, id=id)
    listener, created = Listener.objects.get_or_create(user=request.user)
    if created:
        listener.save()
    state = EpisodePlaybackState(episode=object, listener=listener)
    state.completed = True
    state.save()

    next = request.GET.get('next', reverse('podcasts:podcasts-details', kwargs={'slug': object.podcast.slug}))
    return redirect(next)


@require_POST
def episode_queue_download(request, id):
    site = get_current_site(request)
    object = get_object_or_404(Episode, id=id)
    object.queue_download_task(
        site.podcastssettings.storage_directory,
        site.podcastssettings.naming_scheme
    )
    return HttpResponseNoContent()


@require_POST
def podcast_queue_download(request, slug):
    site = get_current_site(request)
    site.podcastssettings.storage_directory
    object = get_object_or_404(Podcast.objects.prefetch_related('episodes'), slug=slug)
    object.queue_missing_episodes_download_tasks(
        site.podcastssettings.storage_directory,
        site.podcastssettings.naming_scheme
    )
    return HttpResponseNoContent()


class EpisodeDetailsView(RetrieveAPIView):
    queryset = Episode.objects.all()
    lookup_field = 'id'
    serializer_class = EpisodeSerializer


def episode_details(request, id):
    object = get_object_or_404(
        Episode.objects.prefetch_related('podcast', 'chapters'),
        id=id)

    return JsonResponse(EpisodeSerializer(object))


def _episode_content_html(request, id=None, object=None):
    if id is None and object is None:
        raise Exception('Need either an episode ID or object')
    if not object:
        object = get_object_or_404(Episode, id=id)

    isp = request.user.listener.image_security_policy
    if isp == 'a':
        allowed_domains = ['*', ]
    elif isp == 'f':
        domain = utils.clean_link(object.podcast.link)
        allowed_domains = [domain, ]
    else:
        allowed_domains = []

    return object.get_content(allowed_domains)


def apple_podcasts_topcharts(request):
    response = requests.get(ITUNES_TOPCHARTS_URL, headers=HEADERS)
    data = response.json()
    return JsonResponse(unify_apple_podcasts_response(data))


def apple_podcasts_feed_from_id(request, id):
    params = {'id': id}
    url_parts = list(urlparse(ITUNES_LOOKUP_URL))
    url_parts[4] = urlencode(params)
    url = urlunparse(url_parts)
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    if 'resultCount' in data and data['resultCount'] > 0:
        return JsonResponse({'url': data['results'][0]['feedUrl']})


@require_POST
def apple_podcasts_search(request):
    term = request.POST.get('term', '')
    params = {'media': 'podcast', 'term': term, 'limit': ITUNES_SEARCH_LIMIT}

    if len(term) > 2:
        url_parts = list(urlparse(ITUNES_SEARCH_URL))
        url_parts[4] = urlencode(params)
        url = urlunparse(url_parts)
        response = requests.post(url, headers=HEADERS)
        data = response.json()
        return JsonResponse(unify_apple_podcasts_response(data))
