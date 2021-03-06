from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from django.contrib.sites.shortcuts import get_current_site
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Max, Case, When
from django.urls import reverse_lazy
from django.views.generic.list import ListView
from django.views.generic.edit import DeleteView, FormView
from django.http import HttpResponseBadRequest
from podcasts.conf import (PODCASTS_PER_PAGE, EPISODES_PER_PAGE)
from podcasts.forms import NewFromURLForm, ListenerSettingsForm, AdminSettingsForm, SiteSettingsForm
from podcasts.models.podcast import Podcast
from podcasts.models.episode import Episode
from podcasts.utils import handle_uploaded_file, parse_opml_file

from actstream.models import Action


# Create your views here.
def index(request):
    # return render(request, 'index.html')
    return redirect('podcasts:podcasts-list')


class PodcastsList(ListView):
    model = Podcast
    paginate_by = PODCASTS_PER_PAGE
    template_name = 'podcasts-list.html'

    def get_queryset(self, **kwargs):
        user_ordering = self.request.user.listener.sort_order_podcasts
        queryset = (
            Podcast.objects
            .prefetch_related('subscribers', 'subscribers')
            .prefetch_related('followers', 'followers')
            .annotate(num_episodes=Count('episodes'))
            .annotate(downloaded_episodes=Count(Case(
                When(episodes__downloaded__isnull=False, then=1))))
            .annotate(last_episode_date=Max('episodes__published'))
            .filter(followers=self.request.user.listener)
            .order_by(user_ordering)
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class PodcastDetails(ListView):
    model = Episode
    paginate_by = EPISODES_PER_PAGE
    template_name = 'podcasts-details.html'

    def dispatch(self, request, *args, **kwargs):
        self.slug = kwargs.pop('slug', None)
        self.user = request.user
        if not self.slug:
            return HttpResponseBadRequest()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, **kwargs):
        # slug = kwargs.get('slug')
        user_ordering = self.request.user.listener.sort_order_episodes
        self.podcast = get_object_or_404((
            Podcast.objects
            .prefetch_related('episodes', 'episodes')
            .prefetch_related('subscribers', 'subscribers'))
            .annotate(num_episodes=Count('episodes'))
            .annotate(downloaded_episodes=Count(Case(
                When(episodes__downloaded__isnull=False, then=1))))
            .annotate(last_episode_date=Max('episodes__published')),
            slug=self.slug)

        queryset = self.podcast.episodes.order_by(user_ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['podcast'] = self.podcast
        context['user_is_subscriber'] = self.podcast.subscribers.filter(user=self.user).exists()
        return context


class PodcastNew(FormView):
    template_name = 'podcasts-new.html'
    form_class = NewFromURLForm

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        if form.cleaned_data['feed_url']:
            podcast, created = Podcast.objects.get_or_create_from_feed_url(
                form.cleaned_data['feed_url'],
            )
            podcast.add_subscriber(self.request.user.listener)
            podcast.add_follower(self.request.user.listener)

        if 'opml_file' in self.request.FILES:
            tempfile = handle_uploaded_file(self.request.FILES['opml_file'])
            feeds = parse_opml_file(tempfile)

            for feed in feeds:
                # When creating from OPML, episodes have to be created afterwards, to speed up import
                podcast, created = Podcast.objects.get_or_create_from_feed_url(feed,
                                                                               create_episodes=False)
                if podcast is not None:
                    podcast.add_subscriber(self.request.user.listener)
                    podcast.add_follower(self.request.user.listener)

        if form.cleaned_data['feed_url']:
            return redirect('podcasts:podcasts-details', slug=podcast.slug)
        else:
            return redirect('podcasts:podcasts-list')


class PodcastDeleteView(DeleteView):
    model = Podcast
    context_object_name = 'podcast'
    success_url = reverse_lazy('podcasts:podcasts-list')
    template_name = 'podcasts/podcast_check_delete.html'


def podcasts_refresh_feed(request, slug):
    podcast = get_object_or_404(Podcast, slug=slug)
    podcast.update(update_all=True)
    next = request.GET.get('next', '/')
    return redirect(next)


def settings(request):
    current_site_settings = get_current_site(request)
    current_podcasts_settings = current_site_settings.podcastssettings
    if request.method == 'POST':
        listener_form = ListenerSettingsForm(
            request.POST,
            request.FILES,
            instance=request.user.listener,
            prefix='listener')
        app_admin_form = AdminSettingsForm(
            request.POST,
            request.FILES,
            instance=current_podcasts_settings,
            prefix='app')
        site_admin_form = SiteSettingsForm(
            request.POST,
            request.FILES,
            instance=current_site_settings,
            prefix='site')

        if listener_form.is_valid() and app_admin_form.is_valid() and site_admin_form.is_valid():
            listener_form.save()
            app_admin_form.save()
            site_admin_form.save()

            next = request.GET.get('next', '/')
            return redirect(next)
    else:
        listener_form = ListenerSettingsForm(
            instance=request.user.listener,
            prefix='listener')
        app_admin_form = AdminSettingsForm(
            instance=current_podcasts_settings,
            prefix='app')
        site_admin_form = SiteSettingsForm(
            instance=current_site_settings,
            prefix='site')

    return render(request, 'podcasts-settings.html', {'listener_form': listener_form,
                                                      'app_admin_form': app_admin_form,
                                                      'site_admin_form': site_admin_form})


def activity_list(request):
    queryset = Action.objects.all()
    paginator = Paginator(queryset, 50)
    page = request.GET.get('page')

    try:
        items = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        items = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        items = paginator.page(paginator.num_pages)

    is_paginated = paginator.num_pages > 1
    total_number = queryset.count()
    context = {
        'object_list': items,
        'paginator': paginator,
        'is_paginated': is_paginated,
        'total_number': total_number
    }

    return render(request, 'activity-list.html', context)
