from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from podcasts.conf import (DEFAULT_PODCASTS_ORDER, DEFAULT_EPISODES_ORDER,
                           DEFAULT_IMAGE_SECURITY_POLICY, SEEK_FORWARD_BY, SEEK_BACKWARD_BY,)
from podcasts.models import IntegerRangeField

User = get_user_model()


class Listener(models.Model):

    PODCASTS_ORDER_CHOICES = (
        (_('Content'), (
            ('title', _('Title')),)),
        (_('Metadata'), (
            ('last_episode_date', _('Last Published Episode')),
            ('num_episodes', _('Number of Episodes')),)),
    )

    EPISODES_ORDER_CHOICES = (
        (_('Content'), (
            ('title', _('Title')),)),
        (_('Metadata'), (
            ('downloaded', _('Download Date (Earliest First)')),
            ('-downloaded', _('Download Date (Latest First)')),
            ('published', _('Publishing Date (Earliest First)')),
            ('-published', _('Publishing Date (Latest First)')),
            ('itunes_duration', _('Duration (Shortest First)')),
            ('-itunes_duration', _('Duration (Longest First)')),))
    )

    IMAGE_SECURITY_POLICY_CHOICES = (
        ('a', _('Allow All')),
        ('f', _('Allow First-Party')),
        ('n', _('Allow None')),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    subscribed_podcasts = models.ManyToManyField(
        'podcasts.Podcast',
        verbose_name=_('Subscribed Podcasts'),
        related_name='subscribers',
    )
    interested_podcasts = models.ManyToManyField(
        'podcasts.Podcast',
        verbose_name=_('Added Podcasts'),
        related_name='followers',
    )

    # Display settings
    sort_order_podcasts = models.CharField(
        choices=PODCASTS_ORDER_CHOICES,
        default=DEFAULT_PODCASTS_ORDER,
        max_length=16,
        verbose_name=_('Sort Podcasts By'),
        help_text=_('Determines the sorting of podcasts in the podcasts list'),
    )
    sort_order_episodes = models.CharField(
        choices=EPISODES_ORDER_CHOICES,
        default=DEFAULT_EPISODES_ORDER,
        max_length=16,
        verbose_name=_('Sort Episodes By'),
        help_text=_('Determines the sorting of episodes on podcast detail pages'),
    )
    dark_mode = models.BooleanField(
        default=False,
        verbose_name=_('Dark Mode'),
        help_text=_('Reduce eye strain at night, increase awesomeness by day.'),
    )
    image_security_policy = models.CharField(
        choices=IMAGE_SECURITY_POLICY_CHOICES,
        default=DEFAULT_IMAGE_SECURITY_POLICY,
        max_length=1,
        verbose_name=_('Image Security Policy'),
        help_text=_('How to load external images in show notes, etc.'),
    )

    # Settings for future playback functionality
    playback_seek_forward_by = IntegerRangeField(
        null=True,
        blank=True,
        default=SEEK_FORWARD_BY,
        min_value=1,
        max_value=360,
        verbose_name=_('Seek Duration Forward'),
    )
    playback_seek_backward_by = IntegerRangeField(
        null=True,
        blank=True,
        default=SEEK_BACKWARD_BY,
        min_value=1,
        max_value=360,
        verbose_name=_('Seek Duration Backward'),
    )

    def __str__(self):
        return _("User %(user)s") % {'user': self.user.username}

    def has_played(self, episode):
        if not EpisodePlaybackState.objects.get(episode=episode, listener=self):
            return False

    def subscribe_to_podcast(self, podcast):
        self.subscribed_podcasts.add(podcast)
        self.save()

    def follow_podcast(self, podcast):
        self.interested_podcasts.add(podcast)
        self.save()


@receiver(post_save, sender=User)
def create_user_listener(sender, instance, created, **kwargs):
    if created:
        Listener.objects.create(user=instance)


class EpisodePlaybackState(models.Model):
    episode = models.ForeignKey(
        'podcasts.Episode',
        on_delete=models.CASCADE,
        related_name='playbackstates',
    )
    listener = models.ForeignKey(
        Listener,
        on_delete=models.CASCADE,
        related_name='playbackstates',
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Playback Position'),
    )
    completed = models.BooleanField(
        default=False,
        verbose_name=_('Playback Completed'),
    )

    def __str__(self):
        return "%(user)s's state on %(episode)s" % {'user': self.listener,
                                                    'episode': self.episode}
