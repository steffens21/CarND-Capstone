
GAS_DENSITY = 2.858
ONE_MPH = 0.44704

USE_STEER_PID = False 

from yaw_controller import YawController
from lowpass import LowPassFilter
from pid import PID
import math
import rospy


class Controller(object):

    def __init__(self, params):
        self.yaw_controller = YawController(
            wheel_base = params['wheel_base'],
            steer_ratio = params['steer_ratio'],
            min_speed = params['min_speed'],
            max_lat_accel = params['max_lat_accel'],
            max_steer_angle = params['max_steer_angle'])

        self.prev_linear_velocity = 0.0

        self.filter_steer = True
        if self.filter_steer:
            self.steer_filter = LowPassFilter(time_interval=0.1,
                                              time_constant=0.66)

        self.filter_throttle = True
        if self.filter_throttle:
            self.throttle_filter = LowPassFilter(time_interval=0.1,
                                                 time_constant=0.1)

        self.break_constant = 0.33

        self.vehicle_mass = params['vehicle_mass']
        self.fuel_capacity = params['fuel_capacity']
        self.brake_deadband = params['brake_deadband']
        self.wheel_radius = params['wheel_radius']
        self.sample_rate = params['sample_rate']
        self.throttle_pid = PID(
            10.,
            .0,
            5.,
            0,
            1
        )
        self.steer_pid = PID(
            1.5,
            0.0,
            4.0,
            -params['max_steer_angle'],
            params['max_steer_angle']
        )

        self.avg_cte = 0.0
        self.n_controls = 0

        # assume tank is full when computing total mass of car
        self.total_mass = self.vehicle_mass + self.fuel_capacity * GAS_DENSITY

    def control(self, linear_velocity, angular_velocity, current_velocity, cte,
                enabled = True):
        target_linear_velocity = linear_velocity * 0.9
        velocity_diff = target_linear_velocity - current_velocity

        time_interval = 1.0 / self.sample_rate
        self.n_controls += 1

        throttle = 0.0
        brake = 0.0
        steer = 0.0
        if enabled:
            if (current_velocity > linear_velocity and linear_velocity > 1.0) or target_linear_velocity < self.brake_deadband:
                # Brake in torque [N*m]
                acc = velocity_diff/time_interval # Required acceleration
                brake = self.break_constant*max(math.fabs(acc), 0.19) * self.total_mass * self.wheel_radius
                # Reset controllers
                self.throttle_filter.reset()
                self.throttle_pid.reset()
            else:
                throttle = self.throttle_pid.step(velocity_diff, time_interval)

                # Pass the low-pass filter
                if self.filter_throttle:
                    throttle = self.throttle_filter.filt(throttle)

            # Use unfiltered average of pid and yaw controllers as final steer value  
            steer1 = self.steer_pid.step(-cte, time_interval)
            steer2 = self.yaw_controller.get_steering(
                linear_velocity,
                angular_velocity,
                current_velocity
            )

            ## Pass the low-pass filter
            steer = (steer1 + steer2) / 2.0

            self.avg_cte = ((self.n_controls-1)*self.avg_cte + cte)/self.n_controls
            rospy.loginfo("Thr %.3f, Br %.3f, PID %.3f, YAW %.3f, CTE %.3f, AVG CTE %.3f",
                throttle, brake, steer1, steer2, cte, self.avg_cte)

            # Update the previous target
            self.prev_linear_velocity = linear_velocity

        else:
            self.throttle_pid.reset()
            self.steer_pid.reset()
            self.throttle_filter.reset()
            self.steer_filter.reset()

        # Logwarn for Debugging PID
        # run ```rosrun rqt_pt rqt_plot``` and set topics for plotting the actual velocity
        # rospy.logwarn("Throttle : {}".format(throttle))
        # rospy.logwarn("   Brake : {}".format(brake))
        # rospy.logwarn("   Steer : {}".format(steer))
        # rospy.logwarn("--- ")

        return throttle, brake, steer
